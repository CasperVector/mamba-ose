dashboard_ice.py: dashboard.ice
	slice2py dashboard.ice

.PHONY: clean

clean:
	rm -rf Dashboard/
	rm -f dashboard_ice.py
