project(
  'cios-shell',
  'c',
  version: '0.1.0',
  default_options: [
    'c_std=c11',
    'warning_level=2',
  ],
)

# wlroots requires this define to use its headers
add_project_arguments('-DWLR_USE_UNSTABLE', language: 'c')

# Dependencies
wayland_server = dependency('wayland-server')
wayland_protocols = dependency('wayland-protocols')
xkbcommon = dependency('xkbcommon')
pixman = dependency('pixman-1')
libinput = dependency('libinput')
libdrm = dependency('libdrm')
libseat = dependency('libseat')
xcb = dependency('xcb')
wlroots = dependency('wlroots-0.18')
xwayland_dep = dependency('xwayland', required: false)

# wlroots protocol headers need to be in the include path for relative includes
add_project_arguments(
  '-I/usr/include/wlroots-0.18',
  language: 'c',
)

shell_deps = [
  wayland_server,
  wayland_protocols,
  xkbcommon,
  pixman,
  libinput,
  libdrm,
  libseat,
  xcb,
  wlroots,
]

# Source files
shell_sources = files(
  'src/main.c',
  'src/server.c',
  'src/output.c',
  'src/input.c',
  'src/hotkeys.c',
  'src/xwayland.c',
  'src/xdg_shell.c',
  'src/layer_shell.c',
  'src/process.c',
  'src/ipc.c',
  'src/decorations.c',
  'src/gestures.c',
)

executable(
  'cios-shell',
  shell_sources,
  dependencies: shell_deps,
  install: true,
)

# Install session desktop file for LightDM/GDM (Req 12.3)
install_data(
  '../session/cios-shell.desktop',
  install_dir: '/usr/share/wayland-sessions',
)
