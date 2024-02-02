#!../../bin/linux-x86_64/opticsApp

< envPaths
epicsEnvSet EPICS_CA_MAX_ARRAY_BYTES 64008

cd "${TOP}"
dbLoadDatabase "dbd/opticsApp.dbd"
opticsApp_registerRecordDeviceDriver pdbbase

dbLoadRecords("db/hrSeq.db","P=IOC:,N=1,M_PHI1=m1,M_PHI2=m2")
iocInit
seq &hrCtl, "P=IOC:,N=1,M_PHI1=m1,M_PHI2=m2"

