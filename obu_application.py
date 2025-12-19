#!/usr/bin/env python
from socket import MsgFlag
import time, threading
import ITS_maps as map
from application.message_handler import *
from application.obu_commands import *
import application.app_config as app_conf
import application.app_config_obu as app_obu_conf

den_txd = threading.Condition()

#-----------------------------------------------------------------------------------------
# Thread: application transmission - envia DEN quando notificado
#-----------------------------------------------------------------------------------------
def obu_application_txd(obd_2_interface, start_flag, my_system_rxd_queue, ca_service_txd_queue, den_service_txd_queue):

	while not start_flag.isSet():
		time.sleep (1)
	if (app_conf.debug_sys):
		print('STATUS: Ready to start - THREAD: application_txd - NODE: {}'.format(obd_2_interface["node_id"]),'\n')

	# Aguardar notificação para enviar DEN
	while True:
		with den_txd:
			den_txd.wait()
		# Passar map.obu_node em vez de obd_2_interface
		den_event = trigger_event(map.obu_node, 0, 'start')  # CORRETO
		den_service_txd_queue.put(den_event)
		if (app_conf.debug_app_den):
			print ('obu_application_txd - DEN message sent ', den_event)


#-----------------------------------------------------------------------------------------
# Thread: application reception - recebe SPAT, IVIM e DEN
#-----------------------------------------------------------------------------------------
def obu_application_rxd(obd_2_interface, start_flag, services_rxd_queue, my_system_rxd_queue):

	while not start_flag.isSet():
		time.sleep (1)
	if (app_conf.debug_sys):
		print('STATUS: Ready to start - THREAD: application_rxd - NODE: {}'.format(obd_2_interface["node_id"]),'\n')
    
	while True :
		msg_rxd=services_rxd_queue.get()
		
		# Receber mensagens DEN de outros veículos
		if (msg_rxd['msg_type']=="DEN") and (obd_2_interface['node_id'] != msg_rxd['node']):
			if (app_conf.debug_app_den):
				print ('\n....>obu_application_rxd - DEN message received ',msg_rxd)
			my_system_rxd_queue.put(msg_rxd)
		
		# Receber mensagens SPAT do RSU
		elif (msg_rxd['msg_type']=="SPAT"):
			if (app_conf.debug_app_spat):
				print ('\n....>obu_application - SPAT message received ',msg_rxd)
			my_system_rxd_queue.put(msg_rxd)
		
		# Receber mensagens IVIM do RSU
		elif (msg_rxd['msg_type']=="IVIM"):
			if (app_conf.debug_app_ivim):
				print ('\n....>obu_application - IVIM message received ',msg_rxd)
			my_system_rxd_queue.put(msg_rxd)

          
#-----------------------------------------------------------------------------------------
# Thread: my_system - controla o carro com base nas mensagens recebidas
#-----------------------------------------------------------------------------------------
def obu_system(obd_2_interface, start_flag, coordinates, my_system_rxd_queue, movement_control_txd_queue):
	
	while not start_flag.isSet():
		time.sleep (1)
	if (app_conf.debug_sys):
		print('STATUS: Ready to start - THREAD: obu_system - NODE: {}'.format(obd_2_interface["node_id"]),'\n')
    
	#init car 
	open_car(movement_control_txd_queue)
	turn_on_car(movement_control_txd_queue)
	car_move_forward(movement_control_txd_queue)

	while True :
		msg_rxd=my_system_rxd_queue.get()
		
		# Processar mensagens DEN de outros veículos
		if (msg_rxd['msg_type']=='DEN'):
			if (app_conf.debug_app) or (app_conf.debug_obu):
				print ('\nObu_system: DEN received - hazard detected by another vehicle')
			car_move_slower(movement_control_txd_queue)
		
		# Processar mensagens SPAT (semáforos)
		elif (msg_rxd['msg_type']=='SPAT'):
			tls_group = msg_rxd['intersection']['signalGroups']
			movement = msg_rxd['intersection']['movement']
			for key, value in movement.items():
				direction = value['direction']
				if (direction == obd_2_interface['heading']):
					if (tls_group[key]['state']=='red'):
						print ('\ntls is red')
						stop_car (movement_control_txd_queue)
					elif (tls_group[key]['state']=='yellow'):
						print ('\ntls is yellow')
						car_move_very_slow (movement_control_txd_queue)
					elif (tls_group[key]['state']=='green'):
						print ('\ntls is green')	
						car_move_forward(movement_control_txd_queue)
		
		# Processar mensagens IVIM e enviar DEN quando deteta road_works
		elif (msg_rxd['msg_type']=='IVIM'):
			use_case, situation = ivim_message_received (msg_rxd)
			if (use_case == 'vehicle'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: vehicle stopped')
				stop_car(movement_control_txd_queue)
			elif (use_case=='road_works'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('\nIVIM situation: road_works detected - sending DEN to other vehicles')
				car_move_slower(movement_control_txd_queue)
				# Notificar para enviar DEN
				with den_txd:
					den_txd.notify()
			elif (use_case=='weather_condition'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: weather condition')
				car_move_slower(movement_control_txd_queue)
