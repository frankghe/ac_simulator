#ifndef HVAC_H_
#define HVAC_H_

#include "ac_net.h"

/* Thermal model parameters */
#define AMBIENT_TEMP_MIN -20
#define AMBIENT_TEMP_MAX 50
#define AC_COOLING_FACTOR 0.05f
#define AMBIENT_WARMING_FACTOR 0.01f

/* Thermal model parameters */
#define AMBIENT_TEMP 25.0f
#define HVAC_MASS 50.0f
#define HEAT_TRANSFER_COEFF 0.1f

struct hvac_data {
    struct ac_net_data net;
    /* Thermal model parameters */
    float cabin_temp;
    float target_temp;
    float external_temp;
    bool ac_on;
    uint8_t fan_speed;
    bool initialized;
};

extern struct hvac_data hvac_data;

/* Thread stack */
K_THREAD_STACK_DEFINE(hvac_stack, CONFIG_MAIN_STACK_SIZE);

void start_hvac(void);
void stop_hvac(void);

#endif /* HVAC_H_ */ 