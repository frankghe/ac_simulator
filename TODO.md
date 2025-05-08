Code cleanups:
- script to compile all ECUs
- run-ac-simulator to close terminals, not only kill processes
- check that code works on native Linux, not only wsl
- add README in each ECU


Virtual model
- Restructure directories with all ECUs under a dir, and one dir per "model" 
(abstracted python model, actual embedded code), and env models in a separate dir
- Dockerize project
- CU built with NuttX
- Simplified ADAS e2e (adas, breaking, steering, engine, sensor input, carla sim)
- Connect to a DIY board running zephyr (e.g. stm32) for HIL
- Robot for test framework
- CAN message database and code generation such as arxml, for use in zephyr / NuuttX
- Service-oriented communication (some/ip, zettascale) besides CAN messages
- zephyr time synced with silkit time (silkit being the master)
- support for qemu besides native_sim
- decent functional tests for each ECU
- Android auto ECU with AC app
- REST control API (for remote control)
- REST inspection API (for monitoring and debug)
- Add HVAC based on Zephyr with uService interface definition
- integrate with SDV-Labs

Cloud
- Run docker in cloud (GCP or AWS)
- Remote connect to a docker sim running in cloud
- Integration with ci/cd that triggers regression using cloud setup

BUGS
- When launching a new wsl session (after shutdown) and running the script run-ac-simulator.sh, 
all processes come up correctly but lighting panel does not show up (wayland issue). 
Killing the process (control-c) and pressing Enter to relaunch fixes the issue and lihghting GUI how shows