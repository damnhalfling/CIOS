/// Core state machine for the CIOS Shell
/// Tracks system state and drives visual transitions

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum CoreState {
    /// System idle, listening passively — cyan breathing ring
    Idle,
    /// Actively capturing intent — expanding fragmented ring
    Listening,
    /// Processing locally (Ollama/Layer 1) — cyan spinning
    ProcessingLocal,
    /// Cloud intelligence active (AWS/Layer 2) — orange transition
    ProcessingCloud,
    /// Executing task — flow nodes lighting up
    Executing,
    /// Error state — red fragmentation
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TransitionType {
    /// Element materializing (build line-by-line from bottom)
    RezIn,
    /// Element dissolving (shatter into geometric particles)
    Derezz,
    /// State color shift (cyan -> orange -> red)
    ColorShift,
    /// Pulse/breathe animation
    Pulse,
}

pub struct ShellState {
    pub core: CoreState,
    pub transition_progress: f32,
    pub time_elapsed: f64,
    pub disc_rotation: f32,
    pub disc_scale: f32,
    pub grid_pulse_phase: f32,
}

impl ShellState {
    pub fn new() -> Self {
        Self {
            core: CoreState::Idle,
            transition_progress: 0.0,
            time_elapsed: 0.0,
            disc_rotation: 0.0,
            disc_scale: 1.0,
            grid_pulse_phase: 0.0,
        }
    }

    pub fn update(&mut self, dt: f64) {
        self.time_elapsed += dt;
        self.grid_pulse_phase = (self.time_elapsed * 0.5).sin() as f32 * 0.5 + 0.5;

        match self.core {
            CoreState::Idle => {
                // Gentle breathing: scale oscillates 0.95 - 1.05
                self.disc_scale = 1.0 + (self.time_elapsed * 1.2).sin() as f32 * 0.05;
                self.disc_rotation += dt as f32 * 0.1; // Very slow rotation
            }
            CoreState::Listening => {
                // Expanding, faster rotation
                self.disc_scale = 1.2 + (self.time_elapsed * 3.0).sin() as f32 * 0.1;
                self.disc_rotation += dt as f32 * 2.0;
            }
            CoreState::ProcessingLocal => {
                self.disc_scale = 1.0;
                self.disc_rotation += dt as f32 * 5.0; // Fast spin
            }
            CoreState::ProcessingCloud => {
                self.disc_scale = 1.1;
                self.disc_rotation += dt as f32 * 3.0;
            }
            CoreState::Executing => {
                self.disc_scale = 1.0;
                self.disc_rotation += dt as f32 * 1.0;
            }
            CoreState::Error => {
                // Jitter effect
                self.disc_scale = 1.0 + (self.time_elapsed * 20.0).sin() as f32 * 0.02;
                self.disc_rotation += dt as f32 * 0.5;
            }
        }
    }

    /// Get the primary color for current state as [r, g, b, a]
    pub fn primary_color(&self) -> [f32; 4] {
        match self.core {
            CoreState::Idle => [0.0, 0.898, 1.0, 1.0],           // #00E5FF cyan
            CoreState::Listening => [0.0, 0.898, 1.0, 1.0],      // cyan, brighter
            CoreState::ProcessingLocal => [0.0, 0.898, 1.0, 1.0], // cyan
            CoreState::ProcessingCloud => [1.0, 0.427, 0.0, 1.0], // #FF6D00 orange
            CoreState::Executing => [0.0, 0.898, 1.0, 1.0],      // cyan
            CoreState::Error => [1.0, 0.09, 0.267, 1.0],          // #FF1744 red
        }
    }

    pub fn transition_to(&mut self, new_state: CoreState) {
        self.core = new_state;
        self.transition_progress = 0.0;
    }
}
