#!/usr/bin/env python
# #####################################################################################################
# SENDING/RECEIVING APPLICATION THREADS - add your business logic here!
# Note: you can use a single thread, if you prefer, but be carefully when dealing with concurrency.
#######################################################################################################
import time
import threading
import queue
from application.message_handler import *
import application.app_config as app_conf
import application.app_config_rsu as app_rsu_conf
from application.rsu_commands import *
import ITS_maps as maps

#-----------------------------------------------------------------------------------------
# Thread: rsu application transmission - sends IVIM messages when notified
#-----------------------------------------------------------------------------------------
def rsu_application_txd(rsu_interface, start_flag, my_system_rxd_queue, den_service_txd_queue, ivim_service_txd_queue):
    
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: application_txd - NODE: {}'.format(rsu_interface["node_id"]), '\n')

    # Wait for notification to send IVIM (from system thread)
    while True:
        # Check for messages from system thread
        try:
            # Non-blocking check for messages
            msg_rxd = my_system_rxd_queue.get(block=False)
            
            if msg_rxd['msg_type'] == 'DEN_TO_IVIM':
                # Convert DEN event to IVIM format
                event = msg_rxd['event']
                
                # Map hazard subtype to IVIM description
                hazard_mapping = {
                    'potholes': 'road_works',
                    'flooding': 'weather_condition',
                    'ice': 'weather_condition',
                    'debris': 'road_works',
                    'oil_spill': 'road_works',
                    'fog': 'weather_condition',
                    'hail': 'weather_condition'
                }
                
                # Get IVIM description from hazard type or default to 'road_works'
                hazard_type = event.get('hazard_subtype', 'potholes')
                ivim_description = hazard_mapping.get(hazard_type, 'road_works')
                
                if app_conf.debug_app:
                    print(f'\nRSU: Converting DEN to IVIM - {hazard_type} -> {ivim_description}')
                    print(f'Event details: {event}')
                
                # Create IVIM message
                ivim_details = ivim_containers_creation(rsu_interface, ivim_description)
                
                # Enhance IVIM with hazard details
                enhanced_ivim = {
                    **ivim_details,
                    'original_event_id': event.get('event_id'),
                    'hazard_details': {
                        'type': hazard_type,
                        'severity': event.get('severity', 1),
                        'confidence': event.get('confidence', 0.5),
                        'location': event.get('location', {}),
                        'dimensions': event.get('dimensions', {})
                    },
                    'timestamp': time.time(),
                    'source_rsu': rsu_interface["node_id"]
                }
                
                # Trigger IVIM transmission
                ivim_event = trigger_situation('start')
                ivim_event.update(enhanced_ivim)
                
                # Send IVIM
                ivim_service_txd_queue.put(ivim_event)
                
                if app_conf.debug_app_den:
                    print('rsu_application_txd - IVIM message sent ', ivim_event)
                    
        except queue.Empty:
            # No messages to process, sleep briefly
            time.sleep(0.1)
            continue
        except Exception as e:
            print(f'Error in RSU TXD thread: {e}')
            time.sleep(1)

#-----------------------------------------------------------------------------------------
# Thread: rsu application reception - receives DEN messages from OBUs
#-----------------------------------------------------------------------------------------
def rsu_application_rxd(rsu_interface, start_flag, services_rxd_queue, my_system_rxd_queue):
    
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: application_rxd - NODE: {}'.format(rsu_interface["node_id"]), '\n')
    
    while True:
        # Wait for incoming messages
        msg_rxd = services_rxd_queue.get(block=True, timeout=None)
        
        # Process DEN messages from vehicles
        if msg_rxd['msg_type'] == "DEN":
            if app_conf.debug_app_den:
                print('\nRSU: DEN message received from vehicle:', msg_rxd['node'])
                print('Message content:', msg_rxd)
            
            # Extract event information
            if 'event' in msg_rxd:
                event = msg_rxd['event']
                
                # Log event details
                print(f'\n=== RSU Received Hazard Report ===')
                print(f'Event ID: {event.get("event_id")}')
                print(f'Type: {event.get("event_type")}')
                print(f'Hazard: {event.get("hazard_subtype")}')
                print(f'Severity: {event.get("severity")}/5')
                print(f'Confidence: {event.get("confidence"):.2f}')
                
                if 'location' in event:
                    loc = event['location']
                    print(f'Location: ({loc.get("x", "N/A")}, {loc.get("y", "N/A")})')
                
                if 'dimensions' in event:
                    dims = event['dimensions']
                    print(f'Dimensions: {dims}')
                
                print('====================================\n')
            
            # Forward DEN to system thread for processing
            my_system_rxd_queue.put(msg_rxd)
        
        # Process other message types if needed
        elif msg_rxd['msg_type'] == "SPAT":
            if app_conf.debug_app_spat:
                print('\nRSU: SPAT message received (unexpected for RSU)', msg_rxd)
        
        elif msg_rxd['msg_type'] == "IVIM":
            if app_conf.debug_app_ivim:
                print('\nRSU: IVIM message received (unexpected for RSU)', msg_rxd)
        
        elif msg_rxd['msg_type'] == "CA":
            if app_conf.debug_app_ca:
                print('\nRSU: CA message received', msg_rxd)

#-----------------------------------------------------------------------------------------
# Thread: rsu_system - processes received messages and controls RSU behavior
#-----------------------------------------------------------------------------------------
def rsu_system(rsu_interface, start_flag, coordinates, my_system_rxd_queue, rsu_control_txd_queue):
    
    # Initialize RSU
    start_rsu(rsu_control_txd_queue)
    turn_on(rsu_control_txd_queue)
    
    # Active hazards store
    active_hazards = {}
    hazard_timeout = 300  # 5 minutes timeout for hazards
    
    while not start_flag.isSet():
        time.sleep(1)
    
    if app_conf.debug_sys:
        print('STATUS: Ready to start - THREAD: rsu_system - NODE: {}'.format(rsu_interface["node_id"]), '\n')
    
    time.sleep(app_rsu_conf.warm_up_time)
    
    # Periodic cleanup of old hazards
    def cleanup_old_hazards():
        current_time = time.time()
        expired = []
        for hazard_id, hazard_data in active_hazards.items():
            if current_time - hazard_data['last_update'] > hazard_timeout:
                expired.append(hazard_id)
        
        for hazard_id in expired:
            if app_conf.debug_app:
                print(f'RSU: Removing expired hazard {hazard_id}')
            del active_hazards[hazard_id]
    
    while True:
        try:
            # Check for incoming messages (blocking with timeout for periodic cleanup)
            try:
                msg_rxd = my_system_rxd_queue.get(block=True, timeout=10)
            except queue.Empty:
                # Timeout - perform periodic maintenance
                cleanup_old_hazards()
                continue
            
            # Process DEN messages from vehicles
            if msg_rxd['msg_type'] == 'DEN':
                event = msg_rxd.get('event', {})
                event_id = event.get('event_id')
                
                if event_id:
                    current_time = time.time()
                    
                    # Check if this is a new or updated event
                    if event_id in active_hazards:
                        # Update existing hazard
                        active_hazards[event_id]['last_update'] = current_time
                        active_hazards[event_id]['confirmation_count'] += 1
                        
                        # Update severity/confidence based on new report
                        old_hazard = active_hazards[event_id]['event']
                        old_hazard['severity'] = max(old_hazard.get('severity', 1), 
                                                    event.get('severity', 1))
                        old_hazard['confidence'] = min(1.0, 
                                                      old_hazard.get('confidence', 0) + 0.2)
                        
                        if app_conf.debug_app:
                            print(f'\nRSU: Updated hazard {event_id}')
                            print(f'Confirmations: {active_hazards[event_id]["confirmation_count"]}')
                    
                    else:
                        # New hazard
                        active_hazards[event_id] = {
                            'event': event,
                            'first_seen': current_time,
                            'last_update': current_time,
                            'confirmation_count': 1,
                            'forwarded': False
                        }
                        
                        if app_conf.debug_app:
                            print(f'\nRSU: New hazard detected: {event_id}')
                            print(f'Hazard type: {event.get("hazard_subtype")}')
                    
                    # Check if we should forward this as IVIM
                    hazard_data = active_hazards[event_id]
                    
                    # Forward if:
                    # 1. Not forwarded yet AND confidence > threshold OR
                    # 2. Multiple confirmations (>2) OR
                    # 3. High severity (>=4)
                    should_forward = (
                        not hazard_data['forwarded'] and 
                        (
                            event.get('confidence', 0) > 0.6 or
                            hazard_data['confirmation_count'] >= 2 or
                            event.get('severity', 1) >= 4
                        )
                    )
                    
                    if should_forward:
                        # Mark as forwarded
                        active_hazards[event_id]['forwarded'] = True
                        
                        # Prepare message for IVIM conversion
                        forward_msg = {
                            'msg_type': 'DEN_TO_IVIM',
                            'event': event,
                            'original_sender': msg_rxd.get('node'),
                            'timestamp': current_time
                        }
                        
                        # Send to TXD thread for IVIM transmission
                        my_system_rxd_queue.put(forward_msg)
                        
                        if app_conf.debug_app:
                            print(f'\nRSU: Forwarding hazard {event_id} as IVIM')
                            print(f'Reason: Confidence={event.get("confidence"):.2f}, '
                                  f'Confirmations={hazard_data["confirmation_count"]}, '
                                  f'Severity={event.get("severity")}')
                
                # Also log the event details
                if app_conf.debug_app or app_conf.debug_rsu:
                    print(f'\nRSU System: DEN received from vehicle {msg_rxd.get("node")}')
                    print(f'Event ID: {event_id}')
                    print(f'Type: {event.get("event_type")}')
                    print(f'Hazard: {event.get("hazard_subtype")}')
            
            # Handle manual input for testing
            elif msg_rxd.get('msg_type') == 'MANUAL_INPUT':
                # This would come from a user interface thread
                data = msg_rxd.get('data', '')
                
                if data == '1':
                    ivim_description = ['vehicle']
                elif data == '2':
                    ivim_description = ['road_works']
                elif data == '3':
                    ivim_description = ['weather_condition']
                else:
                    continue
                
                # Create manual IVIM
                ivim_event = trigger_situation('start')
                for desc in ivim_description:
                    ivim_details = ivim_containers_creation(rsu_interface, desc)
                    ivim_event.update(ivim_details)
                
                # Add manual flag
                ivim_event['manual_generated'] = True
                
                # Send IVIM
                # Note: In your original code, this should go to ivim_service_txd_queue
                # but since we're in system thread, we need to forward it
                forward_msg = {
                    'msg_type': 'MANUAL_IVIM',
                    'ivim_event': ivim_event
                }
                my_system_rxd_queue.put(forward_msg)
                
        except Exception as e:
            print(f'Error in RSU system thread: {e}')
            import traceback
            traceback.print_exc()
            time.sleep(1)

#-----------------------------------------------------------------------------------------
# Optional: User interface thread for manual control
#-----------------------------------------------------------------------------------------
def rsu_user_interface(start_flag, my_system_rxd_queue):
    """Separate thread for user input to keep main threads clean"""
    
    while not start_flag.isSet():
        time.sleep(1)
    
    time.sleep(app_rsu_conf.warm_up_time)
    
    while True:
        print('\n' + '='*50)
        print('RSU Control Interface')
        print('='*50)
        print('1 - Send vehicle stopped IVIM')
        print('2 - Send roadworks IVIM')
        print('3 - Send weather condition IVIM')
        print('4 - List active hazards')
        print('x - Exit')
        print('='*50)
        
        choice = input('Select option: ').strip()
        
        if choice == 'x':
            break
        elif choice in ['1', '2', '3']:
            # Send to system thread
            my_system_rxd_queue.put({
                'msg_type': 'MANUAL_INPUT',
                'data': choice
            })
            print(f'Manual IVIM command {choice} queued')
        elif choice == '4':
            # This would need access to active_hazards
            # In a real implementation, you'd share this data
            print('Active hazards listing not implemented in this thread')
        else:
            print('Invalid option')
        
        time.sleep(0.5)