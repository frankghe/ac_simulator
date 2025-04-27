/**
 * Simple test program to send a CAN frame using SilKit C API
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>

/* SilKit headers - adapted for the actual installation */
#include "silkit/capi/SilKit.h"
#include "silkit/capi/Can.h"
#include "silkit/capi/Participant.h"
#include "silkit/capi/Orchestration.h"

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

int main(int argc, char** argv)
{
    SilKit_ReturnCode returnCode;
    
    /* Registry URI */
    const char* registryUri = "silkit://localhost:8500";
    
    /* Participant name */
    const char* participantName = "CanSender";
    
    /* CAN network name */
    const char* canNetworkName = "CAN1";
    
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
    
    /* Initialize the lifecycle configuration struct - use the same magic value as in silkit_bridge.py */
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
    
    /* Wait for everything to initialize */
    printf("Waiting 1 second for initialization...\n");
    sleep(1);
    
    /* Create a CAN frame - Properly initialize all fields */
    SilKit_CanFrame canFrame;
    
    /* Initialize the struct properly using SilKit macros */
    SilKit_Struct_Init(SilKit_CanFrame, canFrame);
    
    /* Set CAN frame properties */
    canFrame.id = 0x123;            /* Standard CAN ID */
    canFrame.flags = 0;             /* Standard frame (not extended) */
    canFrame.dlc = 8;               /* 8 data bytes */
    
    /* Prepare the data buffer with a simple message - ensure alignment for SilKit */
    static uint8_t data_buffer[8] __attribute__((aligned(4))) = {1, 2, 3, 4, 5, 6, 7, 8};
    
    /* Set up the data */
    canFrame.data.data = data_buffer;
    canFrame.data.size = 8;
    
    /* Print CAN frame details */
    printf("Sending CAN frame with the following details:\n");
    PrintCanFrame(&canFrame);
    
    /* Send the CAN frame without a user context */
    returnCode = SilKit_CanController_SendFrame(canController, &canFrame, NULL);
    if (returnCode != SilKit_ReturnCode_SUCCESS)
    {
        fprintf(stderr, "Failed to send CAN frame: %s (error code: %d)\n", 
                GetErrorString(returnCode), returnCode);
    }
    else
    {
        printf("CAN frame sent successfully\n");
    }
    
    /* Wait a moment to ensure the frame is sent */
    printf("Waiting 3 seconds before cleanup...\n");
    sleep(3);
    
    /* Clean up */
    printf("Cleaning up resources...\n");
    
    /* Destroy lifecycle service first */
    SilKit_LifecycleService_Stop(lifecycleService, "Normal shutdown");
    printf("Lifecycle stopped.\n");
    
    /* Destroy participant and configuration */
    SilKit_Participant_Destroy(participant);
    SilKit_ParticipantConfiguration_Destroy(participantConfig);
    
    printf("Done.\n");
    return 0;
} 