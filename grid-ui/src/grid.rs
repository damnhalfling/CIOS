/// Grid Background — the infinite coordinate plane
/// Pulsing neon data lines on deep space background

use crate::state::ShellState;

#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct GridUniforms {
    pub time: f32,
    pub resolution: [f32; 2],
    pub pulse_phase: f32,
    pub primary_color: [f32; 4],
}

impl GridUniforms {
    pub fn from_state(state: &ShellState, width: f32, height: f32) -> Self {
        Self {
            time: state.time_elapsed as f32,
            resolution: [width, height],
            pulse_phase: state.grid_pulse_phase,
            primary_color: state.primary_color(),
        }
    }
}
