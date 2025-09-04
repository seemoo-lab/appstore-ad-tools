/**
   Copyright (C) 2025 Lucas Becker and David Breuer

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
 **/

#include "SDL_events.h"
#include "SDL_keycode.h"
#include "SDL_scancode.h"
#include "input_events.h"
#include "scrcpy_otg.h"
#include "events.h"
#include "usb/screen_otg.h"
#include "util/log.h"
#include <SDL2/SDL.h>
#include <ctype.h>
#include <stdlib.h>
#include <strings.h>
#include <time.h> */
#include <unistd.h>

void sleepms(int milliseconds);

enum task_type {
    // initial device setup
    DEVICE_SETUP,
    // hid-based factory reset.
    // This is useful to reset a device in a failed state that does not yet have ADB.
    FACTORY_RESET,
};

struct scrcpy_otg {
    char *serial;
    char *device_type;
    struct sc_usb usb;
    struct sc_aoa aoa;
    struct sc_keyboard_aoa keyboard;
    struct sc_mouse_aoa mouse;
    struct sc_screen_otg screen_otg;
};

static void
sc_usb_on_disconnected(struct sc_usb *usb, void *userdata) {
    (void) usb;
    (void) userdata;

    SDL_Event event;
    event.type = SC_EVENT_USB_DEVICE_DISCONNECTED;
    int ret = SDL_PushEvent(&event);
    if (ret < 0) {
        LOGE("Could not post USB disconnection event: %s", SDL_GetError());
    }
}

void sleepms(int milliseconds) {
    struct timespec ts;
    ts.tv_sec = milliseconds / 1000;
    ts.tv_nsec = (milliseconds % 1000) * 1000000;
    nanosleep(&ts, NULL);
}


static int char_to_key_event(struct sc_key_event *evt, char key) {
    SDL_Scancode sc;
    SDL_Keymod m;

    // check if lower
    if(islower(key)) {
        // SDL_SCANCODE_A is 4, so we can abuse ascii to get it how we need
        sc = (SDL_Scancode) key - 'a' + 4;
        m = KMOD_NONE;
    } else if(isupper(key)) {
        // SDL_SCANCODE_A is 4, so we can abuse ascii to get it how we need
        sc = (SDL_Scancode) key - 'A' + 4;
        m = KMOD_SHIFT;
    } else if(isdigit(key)) {
        // 0 is first in ascii, but last in scancodes, handle extra
        if (key == '0') sc = SDL_SCANCODE_0;
        else sc = (SDL_Scancode) key - '1' + 30;
        m = KMOD_NONE;
    } else if(ispunct(key)) {
        // some keys are on shift +0-1, others have dedicated keys
        LOGE("Punctuation not implemented yet: %c", key);
        return -1;
    } else {
        LOGE("Could not find scancode for: %c", key);
        return -1;
    }

    // update struct with these values
    evt->scancode =  sc_scancode_from_sdl(sc);
    evt->mods_state = sc_mods_state_from_sdl(m);

    return 0;
}

/* Used to send special key codes such as enter, arrows keys etc.*/
static void send_scancode_press(struct scrcpy_otg *s, SDL_Scancode sc, SDL_Keymod mod) {
    struct sc_key_processor *kp = &s->screen_otg.keyboard->key_processor;

    struct sc_key_event evt = {
        .action = sc_action_from_sdl_keyboard_type(SDL_KEYDOWN),
        .scancode = sc_scancode_from_sdl(sc),
        .mods_state = mod,
        .repeat = 0,
    };

    kp->ops->process_key(kp, &evt, SC_SEQUENCE_INVALID);
    sleepms(200);
    evt.action = sc_action_from_sdl_keyboard_type(SDL_KEYUP);
    kp->ops->process_key(kp, &evt, SC_SEQUENCE_INVALID);
}

static void send_key_press(struct scrcpy_otg *s, char chr) {
    struct sc_key_processor *kp = &s->screen_otg.keyboard->key_processor;

    struct sc_key_event evt = {
        .action = sc_action_from_sdl_keyboard_type(SDL_KEYDOWN),
        .repeat = 0,
    };

    char_to_key_event(&evt, chr);

    kp->ops->process_key(kp, &evt, SC_SEQUENCE_INVALID);
    sleepms(200);
    evt.action = sc_action_from_sdl_keyboard_type(SDL_KEYUP);
    kp->ops->process_key(kp, &evt, SC_SEQUENCE_INVALID);
}

static void press_key_seq(struct scrcpy_otg *s, char *chr_seq) {
    for (unsigned long i = 0; i < strlen(chr_seq); i++) {
        send_key_press(s, chr_seq[i]);
        sleepms(200);
    }
}

// this is a really common pattern
static void shift_tab_enter(struct scrcpy_otg *s) {
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);
}

static void mouse_move(struct scrcpy_otg *s, int x, int y) {
    struct sc_mouse_processor *mp = &s->screen_otg.mouse->mouse_processor;

    struct sc_mouse_motion_event evt = {
        // .position not used for HID events
        .xrel = x,
        .yrel = y,
        .buttons_state = sc_mouse_buttons_state_from_sdl(0, true),
    };
    mp->ops->process_mouse_motion(mp, &evt);
}

static void mouse_click(struct scrcpy_otg *s) {
    struct sc_mouse_processor *mp = &s->screen_otg.mouse->mouse_processor;

    struct sc_mouse_click_event evt = {
        // .position not used for HID events
        .action = SC_ACTION_DOWN,
        .button = SC_MOUSE_BUTTON_LEFT,
        .buttons_state = SC_MOUSE_BUTTON_LEFT,
    };
    mp->ops->process_mouse_click(mp, &evt);
    sleepms(200);
    evt.action = SC_ACTION_UP;
    evt.buttons_state = 0;
    mp->ops->process_mouse_click(mp, &evt);
}


static enum scrcpy_exit_code
reconnect_usb_and_accept_adb(struct scrcpy_otg *s) {
    // device will now disconnect and reconnect
    // we still need to ack adb, so we have to reconnect the usb device
    sleepms(1000);

    bool ok = sc_usb_init(&s->usb);
    if (!ok) {
        LOGE("Failed to init USB.");
        return -1;
    }

    struct sc_usb_device usb_device;
    ok = sc_usb_select_device(&s->usb, s->serial, &usb_device);
    if (!ok) {
        LOGE("Failed to find USB device.");
        return -1;
    }

    static const struct sc_usb_callbacks cbs = {
        .on_disconnected = sc_usb_on_disconnected,
    };
    ok = sc_usb_connect(&s->usb, usb_device.device, &cbs, NULL);
    if (!ok) {
        LOGE("Failed to reconnect to USB device.");
        return -1;
    }

    ok = sc_aoa_init(&s->aoa, &s->usb, NULL);
    if (!ok) {
        LOGE("Failed to re-init aoa.");
        return -1;
    }

    ok = sc_keyboard_aoa_init(&s->keyboard, &s->aoa);
    if (!ok) {
        LOGE("Failed to re-init aoa keyboard.");
        return -1;
    }

    ok = sc_mouse_aoa_init(&s->mouse, &s->aoa);
    if (!ok) {
        LOGE("Failed to re-init aoa mouse.");
        return -1;
    }

    ok = sc_aoa_start(&s->aoa);
    if (!ok) {
        LOGE("Failed to re-start aoa.");
        return -1;
    }

    // wait for everything to be up again
    sleepms(1000);

    system("/usr/bin/adb devices -l");

    // wait for adb popup to be there
    sleepms(1000);

    // select "always trust"
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    shift_tab_enter(s); // grant usb debugging permissions

    // return to home screen
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);

    return SCRCPY_EXIT_SUCCESS;
}

static enum scrcpy_exit_code
perform_setup_sequence_g23(struct scrcpy_otg *s) {

    // spam arrow up to wake up screen and reset ui state
    for(int i = 0; i < 100; i++) {
        send_scancode_press(s, SDL_SCANCODE_UP, KMOD_NONE);
        sleepms(2000);
    }

    // click start
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // select language
    send_scancode_press(s, SDL_SCANCODE_UP, KMOD_NONE);
    sleepms(200);
    for(int i = 0; i < 17; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // confirm language
    shift_tab_enter(s);

    // select 'agree necessary'
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    shift_tab_enter(s);

    // skip setup with other device
    shift_tab_enter(s);

    // we have to wait for some networks being discovered, else our layout will be unpredictable
    sleepms(4000);

    // skip wifi
    // networks can fluctuate, so we press arrow down instead
    for(int i = 0; i < 20; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // confirm skipping
    shift_tab_enter(s);
    sleepms(2000);

    // skip date
    shift_tab_enter(s);

    // accept google stuff
    // send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_NONE);
    // sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_END, KMOD_NONE);
    sleepms(1000); // wait for ui effect
    shift_tab_enter(s);

    // select pin entry
    for(int i = 0; i < 2; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // enter pin
    press_key_seq(s, "0000");
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // confirm that this pin is weak
    shift_tab_enter(s);

    // re-enter pin
    press_key_seq(s, "0000");
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // decline smart stuff
    for(int i = 0; i < 4; i++) {
        send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_NONE);
        sleepms(200);
        send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
        sleepms(200);
    }

    // accept theme
    shift_tab_enter(s);
    sleepms(7000); // wait for processing

    // click finish (devices handle initial focus a bit different, so spam down)
    for(int i = 0; i < 5; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    sleepms(7000); // wait for processing
    LOGD("Should now have finished initial setup.");

    // escape to reset focus / keep screen on
    send_scancode_press(s, SDL_SCANCODE_ESCAPE, KMOD_NONE);
    sleepms(500);

    // open up settings meta+I
    send_scancode_press(s, SDL_SCANCODE_I, KMOD_GUI);
    sleepms(2000); // wait for ui effect

    // go down to about phone setting
    for(int i = 0; i < 30; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000);

    // select software information
    for(int i = 0; i < 4; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000);

    // select build number
    // select software information
    for(int i = 0; i < 6; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000);

    for(int i = 0; i < 7; i++) {
        send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
        sleepms(200);
    }

    // enter pin
    press_key_seq(s, "0000");
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // go back to main settings
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);

    // go down for developer options
    send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
    sleepms(200);

    // enter dev settings
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // enable usb debugging
    for(int i = 0; i < 14; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // confirm
    shift_tab_enter(s);

    return reconnect_usb_and_accept_adb(s);
}

static enum scrcpy_exit_code
perform_factory_reset_g23(struct scrcpy_otg *s) {
    // spam arrow up to wake up screen and reset ui state
    for(int i = 0; i < 5; i++) {
        send_scancode_press(s, SDL_SCANCODE_UP, KMOD_NONE);
        sleepms(200);
    }

    // enter pin 4 x 0 + enter
    press_key_seq(s, "0000");
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // wait for ui transition

    // try to leave settings sub menu if already open
    for(int i = 0; i < 5; i++) {
        send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
        sleepms(1000);
    }

    // open up settings meta+I
    send_scancode_press(s, SDL_SCANCODE_I, KMOD_GUI);
    sleepms(2000); // wait for ui effect

    // navigate down to management settings (22x down)
    for(int i = 0; i < 22; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }

    // enter
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // navigate down to reset settings (22x down)
    for(int i = 0; i < 10; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }

    // enter
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // navigate down to factory reset (8x down)
    for(int i = 0; i < 8; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }

    // enter
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // click reset
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    shift_tab_enter(s);

    // enter pin
    press_key_seq(s, "0000");
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // wait for ui transition

    // confirm and reset
    shift_tab_enter(s);

    return SCRCPY_EXIT_SUCCESS;

}

static enum scrcpy_exit_code
perform_setup_sequence_pixel8(struct scrcpy_otg *s) {
    // send escape to wake up screen
    send_scancode_press(s, SDL_SCANCODE_ESCAPE, KMOD_NONE);
    sleepms(500);

    // click "get started", "skip setup with other device"
    for(int i = 0; i < 2; i++) {
        // press shift + tab to select "Get started button"
        shift_tab_enter(s);
    }

    // bypass "Connect to wifi screen"
    // networks can fluctuate, so we press arrow down instead
    for(int i = 0; i < 20; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // click setup offline
    shift_tab_enter(s);

    // click setup continue
    shift_tab_enter(s);

    // press shift+tab to select skip date settings
    shift_tab_enter(s);

    // bypass privacy settings
    send_scancode_press(s, SDL_SCANCODE_END, KMOD_NONE);
    sleepms(1000); // wait for ui effect
    shift_tab_enter(s);

    // bypass warranty display
    shift_tab_enter(s);

    // enter pin 4 x 0 + enter
    press_key_seq(s, "0000");
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // confirm pin 4 x 0 + enter
    press_key_seq(s, "0000");
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(2000);

    // bypass fingerprint
    send_scancode_press(s, SDL_SCANCODE_END, KMOD_NONE);
    sleepms(1000); // wait for ui effect
    // need to skip start button first
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    shift_tab_enter(s);
    // bypass fingerprint confirmation
    shift_tab_enter(s);

    // faceunlock (TODO: faceunlock not supported on all devices I believe)
    send_scancode_press(s, SDL_SCANCODE_END, KMOD_NONE);
    sleepms(1000); // wait for ui effect
    // need to skip start button first
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    shift_tab_enter(s);

    // wait a bit longer for this weird setup screen thingy
    sleepms(60 * 1000);

    // bypass navigation tutorial, need to skip start button first
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_SHIFT);
    sleepms(200);
    shift_tab_enter(s);

    // escape from final screen
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_ALT);
    sleepms(200);

    for(int i = 0; i < 5; i++) {
        send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
        sleepms(1000);
    }

/* ending: */
    // open up settings meta+I
    send_scancode_press(s, SDL_SCANCODE_I, KMOD_GUI);
    sleepms(1000); // wait for ui effect

    // go down to "About phone"
    send_scancode_press(s, SDL_SCANCODE_TAB, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_END, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // wait for ui effect

    // go down to build number

    // bypass "Connect to wifi screen"
    // networks can fluctuate, so we press arrow down instead
    for(int i = 0; i < 20; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    for(int i = 0; i < 8; i++) {
        send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
        sleepms(200);
    }

    // enter pin 4 x 0 + enter
    press_key_seq(s, "0000");
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // wait for ui transition

    // go back to settings main
    send_scancode_press(s, SDL_SCANCODE_LEFT, KMOD_GUI); // this is the back seq
    sleepms(200);

    // go to system settings
    send_scancode_press(s, SDL_SCANCODE_UP, KMOD_NONE);
    sleepms(200);
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // ui transition

    // navigate down to dev settings (9x down)
    for(int i = 0; i < 9; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    // apparently filtered due to security thingy?? -> Fallback to mouse
    // send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(1000); // ui transition

    // neutralize mouse bottom left
    for(int i = 0; i < 500; i++) {
        mouse_move(s, -4, 4);
        sleepms(20);
    }

    // move to dev options
    for(int i = 0; i < 13; i++) {
        mouse_move(s, 4, -4);
        sleepms(20);
    }
    sleepms(200);
    mouse_click(s);

    // enable debugging settings, needs press down 21 then up 4
    for(int i = 0; i < 21; i++) {
        send_scancode_press(s, SDL_SCANCODE_DOWN, KMOD_NONE);
        sleepms(200);
    }
    for(int i = 0; i < 4; i++) {
        send_scancode_press(s, SDL_SCANCODE_UP, KMOD_NONE);
        sleepms(200);
    }
    send_scancode_press(s, SDL_SCANCODE_RETURN, KMOD_NONE);
    sleepms(200);

    // confirm usb debugging
    shift_tab_enter(s);

    return reconnect_usb_and_accept_adb(s);
}

int main(int argc, char** argv) {
    static struct scrcpy_otg scrcpy_otg;
    struct scrcpy_otg *s = &scrcpy_otg;

    sc_set_log_level(SC_LOG_LEVEL_DEBUG);

    // Minimal SDL initialization
    if (SDL_Init(SDL_INIT_EVENTS)) {
        LOGE("Could not initialize SDL: %s", SDL_GetError());
        return SCRCPY_EXIT_FAILURE;
    }

    atexit(SDL_Quit);

    enum scrcpy_exit_code ret = SCRCPY_EXIT_FAILURE;

    struct sc_keyboard_aoa *keyboard = NULL;
    struct sc_mouse_aoa *mouse = NULL;
    struct sc_usb_device usb_device;
    bool usb_device_initialized = false;
    bool usb_connected = false;
    bool aoa_started = false;
    bool aoa_initialized = false;
    enum task_type task = DEVICE_SETUP;

    static const struct sc_usb_callbacks cbs = {
        .on_disconnected = sc_usb_on_disconnected,
    };
    bool ok = sc_usb_init(&s->usb);
    if (!ok) {
        return SCRCPY_EXIT_FAILURE;
    }

    // handle args late so we have usb setup already.
    // we want to print serials to detect if devices are up.
    if(argc < 3) {
        printf("Usage: %s <device_serial> <device_type> [reset]", argv[0]);

        // call usb select to get serials printed
        sc_usb_select_device(&s->usb, "0123456", &usb_device);

        ret = 1;
        goto end;
    }

    // handle "emergency" reset parameter
    if(argc > 3) {
        if(!strcasecmp("reset", argv[3])) {
            task = FACTORY_RESET;
        }
    }

    s->serial = argv[1]; // get serial from argv
    s->device_type = argv[2]; // get device_type from argv

    ok = sc_usb_select_device(&s->usb, s->serial, &usb_device);
    if (!ok) {
        goto end;
    }

    usb_device_initialized = true;

    ok = sc_usb_connect(&s->usb, usb_device.device, &cbs, NULL);
    if (!ok) {
        goto end;
    }
    usb_connected = true;

    ok = sc_aoa_init(&s->aoa, &s->usb, NULL);
    if (!ok) {
        goto end;
    }
    aoa_initialized = true;

    ok = sc_keyboard_aoa_init(&s->keyboard, &s->aoa);
    if (!ok) {
        goto end;
    }
    keyboard = &s->keyboard;

    ok = sc_mouse_aoa_init(&s->mouse, &s->aoa);
    if (!ok) {
        goto end;
    }
    mouse = &s->mouse;

    ok = sc_aoa_start(&s->aoa);
    if (!ok) {
        goto end;
    }
    aoa_started = true;

    struct sc_screen_otg_params params = {
        .keyboard = keyboard,
        .mouse = mouse,
        .window_title = "scrcpy",
        .always_on_top = false,
        .window_x = SC_WINDOW_POSITION_UNDEFINED,
        .window_y = SC_WINDOW_POSITION_UNDEFINED,
        .window_width = 0,
        .window_height = 0,
        .window_borderless = false,
    };

    ok = sc_screen_otg_init(&s->screen_otg, &params);
    if (!ok) {
        goto end;
    }

    // usb_device not needed anymore
    sc_usb_device_destroy(&usb_device);
    usb_device_initialized = false;


    // main task entry point
    if(task == DEVICE_SETUP) {
        if(!strcasecmp(s->device_type, "pixel_8")) {
            ret = perform_setup_sequence_pixel8(s);
        } else if(!strcasecmp(s->device_type, "g23")) {
            ret = perform_setup_sequence_g23(s);
        }
    } else {
        if(!strcasecmp(s->device_type, "pixel_8")) {
            LOGE("Factory reset currently not implemented for pixel_8 devices!");
            ret = SCRCPY_EXIT_FAILURE;
        } else if(!strcasecmp(s->device_type, "g23")) {
            ret = perform_factory_reset_g23(s);
        }
    }

    LOGD("quit...");

end:
    if (aoa_started) {
        sc_aoa_stop(&s->aoa);
    }
    sc_usb_stop(&s->usb);

    if (mouse) {
        sc_mouse_aoa_destroy(&s->mouse);
    }
    if (keyboard) {
        sc_keyboard_aoa_destroy(&s->keyboard);
    }

    if (aoa_initialized) {
        sc_aoa_join(&s->aoa);
        sc_aoa_destroy(&s->aoa);
    }

    sc_usb_join(&s->usb);

    if (usb_connected) {
        sc_usb_disconnect(&s->usb);
    }

    if (usb_device_initialized) {
        sc_usb_device_destroy(&usb_device);
    }

    sc_usb_destroy(&s->usb);

    return ret;
}
