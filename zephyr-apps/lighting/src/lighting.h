#ifndef LIGHTING_H_
#define LIGHTING_H_

#include <zephyr/kernel.h>

/* Lighting states */
#define LIGHT_OFF 0
#define LIGHT_ON 1
#define BLINKER_LEFT 2
#define BLINKER_RIGHT 3
#define HAZARD_LIGHTS 4

struct lighting_data {
    uint8_t headlight_state;
    uint8_t blinker_state;
    uint8_t hazard_state;
    bool initialized;
};

extern struct lighting_data lighting_data;

/* Thread stack */
K_THREAD_STACK_DEFINE(lighting_stack, CONFIG_MAIN_STACK_SIZE);

void start_lighting(void);
void stop_lighting(void);

#endif /* LIGHTING_H_ */