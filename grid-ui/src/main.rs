mod animation;
mod compositor;
mod grid;
mod identity_disc;
mod renderer;
mod shaders;
mod state;
mod transitions;

use log::info;

fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("╔══════════════════════════════════════╗");
    info!("║  CIOS Shell v0.1.0 — The Grid       ║");
    info!("╚══════════════════════════════════════╝");
    info!("");
    info!("Connecting to Wayland compositor...");

    let mut shell = match compositor::CiosShell::new() {
        Ok(s) => s,
        Err(e) => {
            eprintln!("ERROR: Failed to initialize CIOS Shell: {}", e);
            eprintln!("");
            eprintln!("Make sure you are running under a Wayland compositor with");
            eprintln!("wlr-layer-shell support (Sway, Hyprland, etc.)");
            std::process::exit(1);
        }
    };

    info!("Connected. Starting Grid Interface...");
    shell.run();
}
