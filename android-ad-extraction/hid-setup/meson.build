src = [
    'src/hid_setup.c',
    'src/adb/adb.c',
    'src/adb/adb_device.c',
    'src/adb/adb_parser.c',
    'src/adb/adb_tunnel.c',
    'src/audio_player.c',
    'src/cli.c',
    'src/compat.c',
    'src/control_msg.c',
    'src/controller.c',
    'src/decoder.c',
    'src/delay_buffer.c',
    'src/demuxer.c',
    'src/device_msg.c',
    'src/display.c',
    'src/file_pusher.c',
    'src/fps_counter.c',
    'src/frame_buffer.c',
    'src/input_manager.c',
    'src/mouse_sdk.c',
    'src/opengl.c',
    'src/options.c',
    'src/packet_merger.c',
    'src/receiver.c',
    'src/recorder.c',
    'src/screen.c',
    'src/version.c',
    'src/hid/hid_keyboard.c',
    'src/hid/hid_mouse.c',
    'src/trait/frame_source.c',
    'src/trait/packet_source.c',
    'src/uhid/keyboard_uhid.c',
    'src/uhid/mouse_uhid.c',
    'src/uhid/uhid_output.c',
    'src/util/acksync.c',
    'src/util/audiobuf.c',
    'src/util/average.c',
    'src/util/file.c',
    'src/util/intmap.c',
    'src/util/intr.c',
    'src/util/log.c',
    'src/util/memory.c',
    'src/util/net.c',
    'src/util/net_intr.c',
    'src/util/process.c',
    'src/util/process_intr.c',
    'src/util/rand.c',
    'src/util/strbuf.c',
    'src/util/str.c',
    'src/util/term.c',
    'src/util/thread.c',
    'src/util/tick.c',
    'src/util/timeout.c',
    'src/sys/unix/file.c',
    'src/sys/unix/process.c',
    'src/usb/aoa_hid.c',
    'src/usb/keyboard_aoa.c',
    'src/usb/mouse_aoa.c',
    'src/usb/screen_otg.c',
    'src/usb/usb.c',
    ]

conf = configuration_data()

conf.set('_POSIX_C_SOURCE', '200809L')
conf.set('_XOPEN_SOURCE', '700')
conf.set('_GNU_SOURCE', true)

cc = meson.get_compiler('c')

dependencies = [
    dependency('libavformat', version: '>= 57.33'),
    dependency('libavcodec', version: '>= 57.37'),
    dependency('libavutil'),
    dependency('libswresample'),
    dependency('sdl2', version: '>= 2.0.5'),
    dependency('libusb-1.0'),
]

check_functions = [
    'strdup',
    'asprintf',
    'vasprintf',
    'nrand48',
    'jrand48',
    'reallocarray',
]

foreach f : check_functions
  if cc.has_function(f)
    define = 'HAVE_' + f.underscorify().to_upper()
    conf.set(define, true)
  endif
endforeach

conf.set('HAVE_SOCK_CLOEXEC', host_machine.system() != 'windows' and
                              cc.has_header_symbol('sys/socket.h', 'SOCK_CLOEXEC'))

# the version, updated on release
conf.set_quoted('SCRCPY_VERSION', meson.project_version())

# the prefix used during configuration (meson --prefix=PREFIX)
conf.set_quoted('PREFIX', get_option('prefix'))

# enable HID over AOA support (linux only)
conf.set('HAVE_USB', true)

configure_file(configuration: conf, output: 'config.h')

src_dir = include_directories('src')

executable('hid-setup', src,
           dependencies: dependencies,
           include_directories: src_dir,
           install: true,
           c_args: [])

# <https://mesonbuild.com/Builtin-options.html#directories>
datadir = get_option('datadir') # by default 'share'
