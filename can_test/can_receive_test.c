/**
 * Simple test program to receive CAN frames using SilKit C API
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <signal.h>

/* SilKit headers - adapted for the actual installation */
#include "silkit/capi/SilKit.h"
#include "silkit/capi/Can.h"
#include "silkit/capi/Participant.h"
#include "silkit/capi/Orchestration.h"

/* Global flag for controlling program execution */
volatile sig_atomic_t running = 1;

/* Signal handler for clean shutdown */
void signal_handler(int sig) {
    running = 0;
    printf("\nShutting down...\n");
}

/* Convert an error code to string for better diagnostic output */
const char* GetErrorString(SilKit_ReturnCode err)
{
    switch (err)
    {
        case SilKit_ReturnCode_SUCCESS: return "SUCCESS";
        case SilKit_ReturnCode_UNSPECIFIEDERROR: return "UNSPECIFIEDERROR";
        case SilKit_ReturnCode_NOTSUPPORTED: return "NOTSUPPORTED";
        case SilKit_ReturnCode_NOTIMPLEMENTED: return "NOTIMPLEMENTED";
        case SilKit_ReturnCode_BADPARAMETER: return "BADPARAMETER";
        case SilKit_ReturnCode_BUFFERTOOSMALL: return "BUFFERTOOSMALL";
        case SilKit_ReturnCode_TIMEOUT: return "TIMEOUT";
        case SilKit_ReturnCode_UNSUPPORTEDSERVICE: return "UNSUPPORTEDSERVICE";
        case SilKit_ReturnCode_WRONGSTATE: return "WRONGSTATE";
        case SilKit_ReturnCode_TYPECONVERSIONERROR: return "TYPECONVERSIONERROR";
        case SilKit_ReturnCode_CONFIGURATIONERROR: return "CONFIGURATIONERROR";
        case SilKit_ReturnCode_PROTOCOLERROR: return "PROTOCOLERROR";
        case SilKit_ReturnCode_ASSERTIONERROR: return "ASSERTIONERROR";
        case SilKit_ReturnCode_EXTENSIONERROR: return "EXTENSIONERROR";
        case SilKit_ReturnCode_LOGICERROR: return "LOGICERROR";
        case SilKit_ReturnCode_LENGTHERROR: return "LENGTHERROR";
        case SilKit_ReturnCode_OUTOFRANGEERROR: return "OUTOFRANGEERROR";
        default: return "UNKNOWN_ERROR";
    }
}

/* Print details of the CAN frame */
void PrintCanFrame(const SilKit_CanFrame* frame)
{
    if (frame == NULL) {
        printf("CAN Frame is NULL\n");
        return;
    }

    printf("CAN Frame details:\n");
    printf("  ID: 0x%x\n", frame->id);
    printf("  Flags: 0x%x\n", frame->flags);
    printf("  DLC: %u\n", frame->dlc);
    
    if (frame->data.data != NULL) {
        printf("  Data size: %zu\n", frame->data.size);
        printf("  Data: [");
        for (size_t i = 0; i < frame->data.size; i++) {
            printf("%u", frame->data.data[i]);
            if (i < frame->data.size - 1) {
                printf(", ");
            }
        }
        printf("]\n");
    } else {
        printf("  Data: NULL\n");
    }
}

/* Callback for frame receptions */
void CanFrameHandler(void* context, SilKit_CanController* controller, SilKit_CanFrameEvent* frameEvent)
{
    printf("Received CAN frame:\n");
    PrintCanFrame(frameEvent->frame);
}

int main(int argc, char** argv)
{
    SilKit_ReturnCode returnCode;
    
    /* Set up signal handler for clean shutdown */
    signal(SIGINT, signal_handler);
    
    /* Registry URI */
    const char* registryUri = "silkit://localhost:8500";
    
    /* Participant name */
    const char* participantName = "CanReceiver";
    
    /* CAN network name - must match the sender */
    const char* canNetworkName = "CAN1";
    
    printf("CAN receiver starting...\n");
    printf("Press Ctrl+C to exit\n");
    
    /* Configuration */
    SilKit_ParticipantConfiguration* participantConfig = NULL;
    
    /* Create participant configuration from empty JSON string */
    returnCode = SilKit_ParticipantConfiguration_FromString(&participantConfig, "{}");
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to create participant configuration: %s\n", GetErrorString(returnCode));
        return 1;
    }
    printf("Participant configuration created.\n");
    
    /* Create participant */
    SilKit_Participant* participant = NULL;
    returnCode = SilKit_Participant_Create(&participant, participantConfig, participantName, registryUri);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to create participant: %s\n", GetErrorString(returnCode));
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("Participant created.\n");
    
    /* Create lifecycle service */
    SilKit_LifecycleService* lifecycleService = NULL;
    SilKit_LifecycleConfiguration lifecycleConfig;
    
    /* Initialize the lifecycle configuration struct - use the same magic value as in sender */
    memset(&lifecycleConfig, 0, sizeof(lifecycleConfig));
    lifecycleConfig.structHeader.version = ((83ULL << 56) | (75ULL << 48) | (7ULL << 40) | (2ULL << 32) | (1ULL << 24));
    lifecycleConfig.operationMode = SilKit_OperationMode_Autonomous;
    
    /* Create the lifecycle service */
    returnCode = SilKit_LifecycleService_Create(&lifecycleService, participant, &lifecycleConfig);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to create lifecycle service: %s\n", GetErrorString(returnCode));
        SilKit_Participant_Destroy(participant);
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("Lifecycle service created in Autonomous mode.\n");
    
    /* Create CAN controller */
    SilKit_CanController* canController = NULL;
    returnCode = SilKit_CanController_Create(
        &canController,        /* out parameter */
        participant,           /* participant */
        "CanController1",      /* name of the controller */
        canNetworkName         /* network name */
    );
    
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to create CAN controller: %s\n", GetErrorString(returnCode));
        SilKit_Participant_Destroy(participant);
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("CAN controller created.\n");
    
    /* Add frame handler for receiving CAN frames */
    SilKit_HandlerId frameHandlerId = 0;
    returnCode = SilKit_CanController_AddFrameHandler(
        canController,
        NULL, /* context */
        CanFrameHandler, 
        SilKit_Direction_Receive, /* RX = 2 */
        &frameHandlerId);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to add frame handler: %s\n", GetErrorString(returnCode));
        SilKit_Participant_Destroy(participant);
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("Frame handler added.\n");
    
    /* Start CAN controller */
    returnCode = SilKit_CanController_Start(canController);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to start CAN controller: %s\n", GetErrorString(returnCode));
        SilKit_Participant_Destroy(participant);
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("CAN controller started.\n");
    
    /* Start the lifecycle */
    returnCode = SilKit_LifecycleService_StartLifecycle(lifecycleService);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to start lifecycle: %s\n", GetErrorString(returnCode));
        SilKit_Participant_Destroy(participant);
        SilKit_ParticipantConfiguration_Destroy(participantConfig);
        return 1;
    }
    printf("Lifecycle started.\n");
    
    printf("Waiting for CAN frames on network: %s\n", canNetworkName);
    
    /* Main loop - just wait for frames and handle Ctrl+C */
    while (running) {
        sleep(1);
    }
    
    /* Clean up */
    printf("Cleaning up resources...\n");
    
    /* Stop the lifecycle service */
    SilKit_LifecycleService_Stop(lifecycleService, "Normal shutdown");
    printf("Lifecycle stopped.\n");
    
    /* Remove handler */
    SilKit_CanController_RemoveFrameHandler(canController, frameHandlerId);
    
    /* Destroy participant and configuration */
    SilKit_Participant_Destroy(participant);
    SilKit_ParticipantConfiguration_Destroy(participantConfig);
    
    printf("Done.\n");
    return 0;
} 