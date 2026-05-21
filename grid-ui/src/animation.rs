/// Animation system for CIOS Shell
/// Handles timing, easing, and transition orchestration

use std::time::Instant;

#[derive(Debug, Clone, Copy)]
pub enum Easing {
    Linear,
    EaseInQuad,
    EaseOutQuad,
    EaseInOutCubic,
    EaseOutElastic,
}

impl Easing {
    pub fn apply(&self, t: f32) -> f32 {
        let t = t.clamp(0.0, 1.0);
        match self {
            Easing::Linear => t,
            Easing::EaseInQuad => t * t,
            Easing::EaseOutQuad => t * (2.0 - t),
            Easing::EaseInOutCubic => {
                if t < 0.5 {
                    4.0 * t * t * t
                } else {
                    1.0 - (-2.0 * t + 2.0_f32).powi(3) / 2.0
                }
            }
            Easing::EaseOutElastic => {
                if t == 0.0 || t == 1.0 {
                    t
                } else {
                    let p = 0.3;
                    (2.0_f32).powf(-10.0 * t)
                        * ((t - p / 4.0) * (2.0 * std::f32::consts::PI / p)).sin()
                        + 1.0
                }
            }
        }
    }
}

#[derive(Debug, Clone)]
pub struct Animation {
    pub start_time: Instant,
    pub duration_ms: u64,
    pub easing: Easing,
    pub from: f32,
    pub to: f32,
    pub completed: bool,
}

impl Animation {
    pub fn new(from: f32, to: f32, duration_ms: u64, easing: Easing) -> Self {
        Self {
            start_time: Instant::now(),
            duration_ms,
            easing,
            from,
            to,
            completed: false,
        }
    }

    pub fn value(&mut self) -> f32 {
        let elapsed = self.start_time.elapsed().as_millis() as f64;
        let t = (elapsed / self.duration_ms as f64).min(1.0) as f32;

        if t >= 1.0 {
            self.completed = true;
            return self.to;
        }

        let eased = self.easing.apply(t);
        self.from + (self.to - self.from) * eased
    }

    pub fn is_complete(&self) -> bool {
        self.completed || self.start_time.elapsed().as_millis() >= self.duration_ms as u128
    }
}

/// Manages multiple concurrent animations
pub struct AnimationController {
    pub rez_in: Option<Animation>,
    pub derezz: Option<Animation>,
    pub color_shift: Option<ColorShiftAnimation>,
    pub disc_pulse: f32,
}

#[derive(Debug, Clone)]
pub struct ColorShiftAnimation {
    pub animation: Animation,
    pub from_color: [f32; 4],
    pub to_color: [f32; 4],
}

impl ColorShiftAnimation {
    pub fn current_color(&mut self) -> [f32; 4] {
        let t = self.animation.value();
        [
            self.from_color[0] + (self.to_color[0] - self.from_color[0]) * t,
            self.from_color[1] + (self.to_color[1] - self.from_color[1]) * t,
            self.from_color[2] + (self.to_color[2] - self.from_color[2]) * t,
            self.from_color[3] + (self.to_color[3] - self.from_color[3]) * t,
        ]
    }
}

impl AnimationController {
    pub fn new() -> Self {
        Self {
            rez_in: None,
            derezz: None,
            color_shift: None,
            disc_pulse: 0.0,
        }
    }

    pub fn start_rez_in(&mut self, duration_ms: u64) {
        self.rez_in = Some(Animation::new(0.0, 1.0, duration_ms, Easing::EaseOutQuad));
    }

    pub fn start_derezz(&mut self, duration_ms: u64) {
        self.derezz = Some(Animation::new(0.0, 1.0, duration_ms, Easing::EaseInQuad));
    }

    pub fn start_color_shift(&mut self, from: [f32; 4], to: [f32; 4], duration_ms: u64) {
        self.color_shift = Some(ColorShiftAnimation {
            animation: Animation::new(0.0, 1.0, duration_ms, Easing::EaseInOutCubic),
            from_color: from,
            to_color: to,
        });
    }

    pub fn update(&mut self) {
        // Clean up completed animations
        if let Some(ref anim) = self.rez_in {
            if anim.is_complete() {
                self.rez_in = None;
            }
        }
        if let Some(ref anim) = self.derezz {
            if anim.is_complete() {
                self.derezz = None;
            }
        }
        if let Some(ref cs) = self.color_shift {
            if cs.animation.is_complete() {
                self.color_shift = None;
            }
        }
    }
}
