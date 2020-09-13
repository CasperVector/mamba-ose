.PHONY: clean all ice
all: ice

ice:
	slice2py -Islices/ slices/types.ice slices/dashboard.ice slices/experiment.ice

clean:
	rm -rf Dashboard/
	rm -f dashboard_ice.py
