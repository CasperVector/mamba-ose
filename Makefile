.PHONY: clean all ice
all: ice logs

ice:
	slice2py --underscore -Islices/ slices/types.ice slices/dashboard.ice slices/experiment.ice

logs:
	mkdir logs/

clean:
	rm -rf MambaICE/
	rm -rf logs/
