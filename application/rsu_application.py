#!/usr/bin/env python
# #####################################################################################################
# SENDING/RECEIVING APPLICATION THREADS - add your business logic here!
# Note: you can use a single thread, if you prefer, but be carefully when dealing with concurrency.
#######################################################################################################
from socket import MsgFlag
import time, threading
from application.message_handler import *
import application.app_config as app_conf
import application.app_config_rsu as app_rsu_conf
from application.rsu_commands import *
import application.event_config as event_conf
import ITS_maps as maps
from dataclasses import dataclass, field
import math

LOCATION_RADIUS = 20

def is_in_zone(loc1: dict, loc2: dict, radius: float) -> bool:
    if loc1 is None or loc2 is None:
        return False
    
    dx = loc1['x'] - loc2['x']
    dy = loc1['y'] - loc2['y']
    return math.hypot(dx, dy) <= radius

den_txd = threading.Condition()

status_update = threading.Condition()

#-----------------------------------------------------------------------------------------
# Thread: rsu application transmission. In this example user triggers CA and DEN messages. 
#   to be completed, in case RSU sends messages
#        my_system_rxd_queue to send commands/messages to rsu_system
#        ca_service_txd_queue to send CA messages
#        den_service_txd_queue to send DEN messages
#-----------------------------------------------------------------------------------------
def rsu_application_txd(rsu_interface, start_flag, my_system_out_queue, ca_service_txd_queue, den_service_txd_queue, ivim_service_txd_queue, spat_service_txd_queue):
    
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: application_txd - NODE: {}'.format(rsu_interface["node_id"]), '\n')
    
    while True:
        print("RSU TXD: Waiting for DEN to echo as IVIM...\n")
        try:
            # Wait for messages from system thread to send as IVIM
            with den_txd:
                den_txd.wait()
            msg_rxd = my_system_out_queue.get(block=True, timeout=None)
            print("RSU TXD: Received message from system thread:", msg_rxd, "\n")
            
            if msg_rxd['msg_type'] == 'ECHO_IVIM':
                # This message comes from rsu_system, contains the event to echo
                event_msg = msg_rxd['event']
                event = event_conf.EventConfig(
                    event_id=event_msg['event_id'],
                    event_type=event_conf.EventType(event_msg['event_type']),
                    hazard_subtype=event_conf.HazardSubType(event_msg['hazard_subtype']) if event_msg['hazard_subtype'] is not None else None,
                    severity=event_msg['severity'],
                    confidence=event_msg['confidence'],
                    location=event_msg['location'],
                    dimensions=event_msg['dimensions'],
                    max_hops=event_msg['max_hops'],
                    max_latency=event_msg['max_latency'])
                
                if app_conf.debug_app:
                    print(f'\nRSU TXD: Creating IVIM from DEN event')
                    print(f'Event type: ', event_msg['event_type'])
                    print(f'Hazard: ', event_msg['hazard_subtype'])
                # Create IVIM message
                ivim_event = trigger_situation(map.rsu_node, event)
                # Send IVIM
                ivim_service_txd_queue.put(ivim_event)
                print("RSU TXD: IVIM message put to ivim_service_txd_queue\n")
                print(ivim_event)
                if app_conf.debug_app_den:
                    print('rsu_application_txd - IVIM message sent')
                    
        except Exception as e:
            print(f'Error in RSU TXD thread: {e}')
            time.sleep(1)
    
                


#-----------------------------------------------------------------------------------------
# Thread: rsu application reception. In this example it does not send ot receive messages
#   to be completed, in case RSU receives messages
#   use: services_rxd_queue to receive messages
#        my_system_rxd_queue to send commands/messages to rsu_system
#-----------------------------------------------------------------------------------------
def rsu_application_rxd(rsu_interface, start_flag, services_rxd_queue, my_system_in_queue):
     
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: application_rxd - NODE: {}'.format(rsu_interface["node_id"]), '\n')
    
    while True:
        # Wait for incoming messages
        msg_rxd = services_rxd_queue.get(block=True, timeout=None)
        print("RSU RXD: Received message:", msg_rxd, "\n")
        
        # Process DEN messages from vehicles
        if msg_rxd['msg_type'] == "DEN":
            if app_conf.debug_app_den:
                print('\nRSU RXD: DEN message received from vehicle:', msg_rxd['node'])
            
            # Simply forward to system thread
            my_system_in_queue.put(msg_rxd)

            


#-----------------------------------------------------------------------------------------
# Thread: my_system - car remote control (test of the functions needed to control your car)
# The car implements a finite state machine. This means that the commands must be executed in the right other.
# Initial state: closed
# closed   - > opened                       opened -> closed | ready:                   ready ->  not_ready | moving   
# not_ready -> stopped | ready| closed      moving -> stopped | not_ready | closed      stopped -> moving not_ready | closed
#-----------------------------------------------------------------------------------------
def rsu_system(rsu_interface, start_flag, coordinates, my_system_in_queue, rsu_control_txd_queue, my_system_out_queue):
    
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: my_system - NODE: {}'.format(rsu_interface["node_id"]), '\n')
    
    time.sleep(app_rsu_conf.warm_up_time)
    
    # Initialize RSU
    start_rsu(rsu_control_txd_queue)
    turn_on(rsu_control_txd_queue)
    
    print(f'\nRSU System: Ready to echo DEN to IVIM\n')
    
    # Array de struct com event_type, location e confidence
    #@dataclass
    #class StoredEvent:
     #   event_type: event_conf.EventType
      #  location: event_conf.Optional[event_conf.Dict[str, float]] = None 
      #  confidence: float = 0
      #  node_IDs: list[str] = field(default_factory = list)

    EventArray = []

    while True:
        # Wait for messages from RXD thread
        msg_rxd = my_system_in_queue.get(block=True)
        print("RSU System: Received message from RXD thread:", msg_rxd, "\n")
        
        # If it's a DEN message, echo it as IVIM
        if msg_rxd['msg_type'] == 'DEN':
            event_rxd = msg_rxd.get('event', {})
            
            # Log the received DEN
            print(f'\n=== RSU Echo System ===')
            print(f'Received DEN from vehicle: {msg_rxd.get("node")}')
            print(f'Event ID: {event_rxd.get("event_id")}')
            
            # Get location, event_type and confidence e agregar ao array
            #new_EventType = msg_rxd.get("event_type")
            new_EventType = event_rxd["event_type"]
            #new_Location = msg_rxd.get("location")
            new_Location = event_rxd["location"]
            #new_Confidence = msg_rxd.get("confidence")
            new_Confidence = event_rxd["confidence"]
            new_Node_ID = msg_rxd.get("node")

            # Procurar por um evento igual existente no array, se existir aumentar a confidence
            event_X = None
            for e in EventArray:
                clause1 = e.get("event_type") == new_EventType
                clause2 = is_in_zone(e.get("location"), new_Location, LOCATION_RADIUS)

                '''
                print("\nChecking event:", e.get("event_id"))
                print("  First Clause (event_type):", clause1)
                print("  Second Clause (location):", clause2)
                print("  Third Clause (node):", clause3)
                print('=======================\n')
                '''

                #print('Message rxd: ', msg_rxd)
                #print('=======================\n')

                if clause1 and clause2:
                    event_X = e
                    break

            if event_X is not None:
                if new_Node_ID not in event_X.get("node", []):
                    event_X["confidence"] += new_Confidence
                    event_X["node"].append(new_Node_ID)
                    event = event_X
                else:
                    pass

            else:
            # Se não existe nenhum evento no array que corresponda aos dados, criar um novo
                #new_Event = StoredEvent(event_type = new_EventType, location = new_Location, confidence = new_Confidence)
                #new_Event.node_IDs.append(new_Node_ID)
                event_rxd["node"] = [new_Node_ID]
                EventArray.append(event_rxd)
                event = event_rxd

            print('Printing EventArray')
            print(EventArray)
            print('=======================\n')

            print('\nEvent Confidence:', event["confidence"], '\n')

            print('Echoing as IVIM message...')
            print('=======================\n')
            print('Event')
            
            # Create echo message for TXD thread
            echo_msg = {
                'msg_type': 'ECHO_IVIM',
                'event': event,
                'original_sender': msg_rxd.get('node'),
                'timestamp': time.time()
            }
            
            # Send to TXD thread to transmit as IVIM
            print("putting echo message to my_system_rxd_queue\n")
            my_system_out_queue.put(echo_msg)
            with den_txd:
                den_txd.notify()