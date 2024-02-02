#!/bin/sh -
#
# $ (cd /opt/epics/simDetectorIOC/iocBoot/iocSimDetector && \
#       ../../bin/linux-x86_64/simDetectorApp ./st.cmd)
# $ (cd /opt/epics/motorSimIOC/iocBoot/iocMotorSim && \
#       ../../bin/linux-x86_64/motorSim ./st.cmd)
# $ (cd /opt/epics/optics/iocBoot/iocOptics && \
#       ../../bin/linux-x86_64/opticsApp /path/to/hr_ioc.cmd)
# $ /path/to/hr_fill.sh && softIoc -d /path/to/hr_k648x.db

caput -c IOC:m1 0
caput -c IOC:m2 0
caput IOC:HR1_UseSetBO Set
caput IOC:HR1_1TypeMO "Silicon"
caput IOC:HR1_H1AO 1
caput IOC:HR1_K1AO 1
caput IOC:HR1_L1AO 1
caput IOC:HR1_2TypeMO "Silicon"
caput IOC:HR1_H2AO 1
caput IOC:HR1_K2AO 1
caput IOC:HR1_L2AO 1
caput IOC:HR1_GeomMO "Symmetric"
caput IOC:HR1_Mode2MO "Theta1 and 2"
sleep 0.5
caput IOC:HR1_EAO 9.6586
sleep 0.5
caget IOC:HR1_ERdbkAO
caput IOC:HR1_UseSetBO Use
caput IOC:HR1_ModeBO Auto

