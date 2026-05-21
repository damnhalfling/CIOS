/// Identity Disc — the central visual element of CIOS Shell
/// Represents the CIOS runtime state as a TRON-style disc

use crate::state::{CoreState, ShellState};

/// Configuration for the Identity Disc rendering
#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct DiscUniforms {
    pub time: f32,
    pub rotation: f32,
    pub scale: f32,
    pub state: u32,
    pub primary_color: [f32; 4],
    pub resolution: [f32; 2],
    pub _padding: [f32; 2],
}

impl DiscUniforms {
    pub fn from_state(state: &ShellState, width: f32, height: f32) -> Self {
        let state_id = match state.core {
            CoreState::Idle => 0,
            CoreState::Listening => 1,
            CoreState::ProcessingLocal => 2,
            CoreState::ProcessingCloud => 3,
            CoreState::Executing => 4,
            CoreState::Error => 5,
        };

        Self {
            time: state.time_elapsed as f32,
            rotation: state.disc_rotation,
            scale: state.disc_scale,
            state: state_id,
            primary_color: state.primary_color(),
            resolution: [width, height],
            _padding: [0.0, 0.0],
        }
    }
}
