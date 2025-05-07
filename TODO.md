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
- Add support for qemu besides native_sim
- Add decent functional tests for each ECU

Cloud
- Run docker in cloud (GCP or AWS)
- Remote connect to a docker sim running in cloud
- Integration with ci/cd that triggers regression using cloud setup