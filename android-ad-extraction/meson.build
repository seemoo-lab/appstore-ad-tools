project('hid-setup', 'c',
        version: '1.0',
        meson_version: '>= 0.48',
        default_options: [
            'c_std=c11',
            'warning_level=2',
            'b_ndebug=if-release',
        ])

add_project_arguments('-Wmissing-prototypes', language: 'c')
subdir('hid-setup')
