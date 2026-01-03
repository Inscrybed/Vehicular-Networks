#!/usr/bin/env python
from socket import MsgFlag
import time, threading
import ITS_maps as map
from application.message_handler import *
from application.obu_commands import *
import application.app_config as app_conf
import application.app_config_obu as app_obu_conf
import application.event_config as event_conf
den_txd = threading.Condition()

#-----------------------------------------------------------------------------------------
# Thread: application transmission - envia DEN quando notificado
#-----------------------------------------------------------------------------------------
def obu_application_txd(obd_2_interface, start_flag, my_system_rxd_queue, ca_service_txd_queue, den_service_txd_queue, coordinates ):
	x,y,t = position_read(coordinates)
	while not start_flag.isSet():
		time.sleep (1)
	if (app_conf.debug_sys):
		print('STATUS: Ready to start - THREAD: application_txd - NODE: {}'.format(obd_2_interface["node_id"]),'\n')

	# Aguardar notificação para enviar DEN
	while True:
		with den_txd:
			print("Preso no WHILE\n")
			den_txd.wait()
		print("Cheguei obu_application_txd\n")
		# Passar map.obu_node em vez de obd_2_interface
		#PROCESSAMENTO SENSOR (LATITUDE, LONGITUDE DO PERIGO)
		event = event_conf.EventConfig.create_hazard_event(
                            event_type=event_conf.EventType.ROAD_SURFACE_HAZARD,
							hazard_subtype=event_conf.HazardSubType.FLOODING,
							severity=4, 
							confidence=0.7,
							location={
								'x': x,
								'y': y
							},
							dimensions={
								'depth': 100,
								'estimated_area': 10.0 
							})
		den_event = trigger_event(obd_2_interface["node_id"], event)  # CORRETO             map.obu_node
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
		
		print('Received services message')
		print(msg_rxd)
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
			#print('IVIM message received in obu_application_rxd')
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
	
	my_system_rxd_queue.put({"msg_type": "INIT"})
	
	while True :
		msg_rxd=my_system_rxd_queue.get(block=True, timeout=None)
	
		with den_txd:
			print("Entrei aqui.\n")
			time.sleep(10)
			den_txd.notify()
			print("Entrei aqui v2.\n")

		# Processar mensagens DEN de outros veículos
		if (msg_rxd['msg_type']=='DEN'):
			event = msg_rxd['event']
			event_id = event['event_id']
			event_type = event['event_type']
			hazard_subtype = event['hazard_subtype']
			status = event['status']
			severity = event['severity']
			confidence = event['confidence']
			if (app_conf.debug_app) or (app_conf.debug_obu):
				print ('\nObu_system: DEN received - hazard detected by another vehicle')
				print("Keys:", msg_rxd.keys())
				#print('\n', event, '\n')
				print ('\n', event_id, event_type, hazard_subtype, status, severity, confidence, '\n')
			
			#Comportamento a vir da OBU está igual à RSU: suposto?
			movement_change(movement_control_txd_queue, severity, confidence)

		# Processar mensagens IVIM e enviar DEN quando deteta road_works
		elif (msg_rxd['msg_type']=='IVIM'):
			use_case = msg_rxd['situation']['event_type']
			situation = msg_rxd['situation']['hazard_subtype']
			severity = msg_rxd['situation']['severity']
			confidence = msg_rxd['situation']['confidence']
			#use_case, situation = ivim_message_received(msg_rxd)
			if (use_case == 'road_surface_hazard'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: Road surface hazard')
				#stop_car(movement_control_txd_queue)
			elif (use_case=='vehicle_breakdown'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: Vehicle breakdown')
				#car_turn_right(movement_control_txd_queue)
				# Notificar para enviar DEN
				#with den_txd:
					#den_txd.notify()
			elif (use_case=='weather_hazard'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: weather hazard')

			elif (use_case=='traffic_condition'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: traffic condition')
			
			elif (use_case=='road_works'):
				if (app_conf.debug_app) or (app_conf.debug_obu):
					print ('IVIM situation: road_works detected')
				#car_move_slower(movement_control_txd_queue)
			
			movement_change(movement_control_txd_queue, severity, confidence)
		
		else:
			print('Received message not IVIM nor DEN')
			print(msg_rxd)
		# Processar mensagens SPAT (semáforos)
		'''
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
		'''

def calculate_event_location(x_vehicle, y_vehicle, heading, distance):
	if heading == "N":
		x_event = x_vehicle
		y_event = y_vehicle + distance
	elif heading == "S":
		x_event = x_vehicle
		y_event = y_vehicle - distance
	elif heading == "E":
		x_event = x_vehicle + distance
		y_event = y_vehicle
	elif heading == "O":
		x_event = x_vehicle - distance
		y_event = y_vehicle
	else:
		x_event = x_vehicle
		y_event = y_vehicle
	return x_event, y_event