/// Transition effects — Rez-in and Derezz
/// Visual feedback for element creation and destruction

#[repr(C)]
#[derive(Debug, Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
pub struct TransitionUniforms {
    pub time: f32,
    pub progress: f32,
    pub direction: u32, // 0 = derezz, 1 = rez_in
    pub _pad: u32,
    pub primary_color: [f32; 4],
    pub resolution: [f32; 2],
    pub element_bounds: [f32; 4], // x, y, w, h (normalized)
    pub _pad2: [f32; 2],
}

impl TransitionUniforms {
    pub fn new_derezz(time: f32, progress: f32, color: [f32; 4], res: [f32; 2]) -> Self {
        Self {
            time,
            progress,
            direction: 0,
            _pad: 0,
            primary_color: color,
            resolution: res,
            element_bounds: [0.0, 0.0, 1.0, 1.0],
            _pad2: [0.0, 0.0],
        }
    }

    pub fn new_rez_in(time: f32, progress: f32, color: [f32; 4], res: [f32; 2]) -> Self {
        Self {
            time,
            progress,
            direction: 1,
            _pad: 0,
            primary_color: color,
            resolution: res,
            element_bounds: [0.0, 0.0, 1.0, 1.0],
            _pad2: [0.0, 0.0],
        }
    }
}
