default: cfgutil

cfgutil:
	mkdir -p bin
	cp /Applications/Apple\ Configurator.app/Contents/MacOS/cfgutil bin/
	cp -R /Applications/Apple\ Configurator.app/Contents/Frameworks .
	bspatch bin/cfgutil bin/cfgutil_PATCHED patch
	chmod +x bin/cfgutil_PATCHED
	rm bin/cfgutil
	codesign -s - bin/cfgutil_PATCHED

clean:
	rm -rf Frameworks
	rm -rf bin