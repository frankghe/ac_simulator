/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef CAN_IDS_H_
#define CAN_IDS_H_

/* Lighting System CAN IDs */
#define LIGHTING_CONTROL_ID  0x110  /* Control message for lighting */
#define LIGHTING_STATUS_ID   0x111  /* Status message from lighting ECU */

/* HVAC System CAN IDs */
#define HVAC_CONTROL_ID      0x123  /* Legacy AC control message */
#define HVAC_STATUS_ID       0x125  /* Thermal model status */
#define HVAC_AC_STATUS_ID    0xAC1  /* AC status message */
#define HVAC_POWER_STATUS_ID 0xAC2  /* AC power status */

#endif /* CAN_IDS_H_ */ 