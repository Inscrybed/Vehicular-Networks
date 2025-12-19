#!/usr/bin/env python
# #####################################################################################################
# APP CONFIGURATION PARAMETERS -
#######################################################################################################


#------------------------------------------------------------------------------------------
#include here any specific configuration of the application
#------------------------------------------------------------------------------------------

#-----------------------------------------------------------------------------------------
# Car control
#-----------------------------------------------------------------------------------------
#definir aqui a informacao necessaria à configuracao duma OBU
warm_up_time = 10

# Por exemplo: parametros do movimento. 
movement_update_time = 1

# event_number = 0: evento de road_works detetado via IVIM
event_type = ['Obstacle', 'Rain', 'Hail', 'Hole', 'Fload']           # tipo de evento
status = ['start', 'update', 'cancel']                   # status do evento
rep_interval = [10]                  # intervalo de repetição em segundos
n_hops = [3]                         # número de saltos permitidos (quantos veículos podem retransmitir)
roi_x = [0]                          # região de interesse X (offset em relação à posição do veículo)
roi_y = [0]                          # região de interesse Y (offset em relação à posição do veículo)
latency = [100]                      # latência máxima em milissegundos
intensity = ['very low', 'low', 'medium', 'high', 'very high']
trust = ['low', 'high']