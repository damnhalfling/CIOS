// CIOS Derezz/Rez-in Transition Shader
// Particle dissolution and materialization effects

struct TransitionUniforms {
    time: f32,
    progress: f32, // 0.0 = fully visible, 1.0 = fully dissolved
    direction: u32, // 0 = derezz (dissolve), 1 = rez_in (materialize)
    primary_color: vec4<f32>,
    resolution: vec2<f32>,
    element_bounds: vec4<f32>, // x, y, width, height of element
}

@group(0) @binding(0) var<uniform> u: TransitionUniforms;
@group(0) @binding(1) var source_texture: texture_2d<f32>;
@group(0) @binding(2) var source_sampler: sampler;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
}

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var positions = array<vec2<f32>, 6>(
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, -1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, -1.0),
        vec2<f32>(1.0, 1.0),
        vec2<f32>(-1.0, 1.0),
    );

    var out: VertexOutput;
    out.position = vec4<f32>(positions[vertex_index], 0.0, 1.0);
    out.uv = positions[vertex_index] * 0.5 + 0.5;
    return out;
}

// Hash function for pseudo-random
fn hash(p: vec2<f32>) -> f32 {
    return fract(sin(dot(p, vec2<f32>(12.9898, 78.233))) * 43758.5453);
}

// Particle grid - breaks element into geometric fragments
fn particle_mask(uv: vec2<f32>, progress: f32, time: f32) -> f32 {
    let grid_size = 30.0;
    let cell = floor(uv * grid_size);
    let cell_uv = fract(uv * grid_size);

    // Each cell has a random threshold for when it dissolves
    let threshold = hash(cell);

    // Cells dissolve based on progress and their threshold
    let dissolve = step(threshold, progress);

    // Geometric particle shape within cell
    let particle_shape = step(0.1, cell_uv.x) * step(cell_uv.x, 0.9) *
                         step(0.1, cell_uv.y) * step(cell_uv.y, 0.9);

    return mix(1.0, particle_shape * (1.0 - dissolve), progress);
}

// Falling particles effect during derezz
fn falling_particles(uv: vec2<f32>, progress: f32, time: f32) -> f32 {
    var intensity = 0.0;
    let grid_size = 30.0;

    for (var i = 0; i < 20; i++) {
        let fi = f32(i);
        let seed = vec2<f32>(fi * 7.13, fi * 3.71);
        let start_x = hash(seed);
        let start_y = hash(seed + 1.0);

        // Particle falls when progress passes its threshold
        let threshold = hash(seed + 2.0);
        let fall_progress = clamp((progress - threshold) * 3.0, 0.0, 1.0);

        let px = start_x + sin(time + fi) * 0.02;
        let py = start_y + fall_progress * 0.5; // Fall down

        let dist = length(uv - vec2<f32>(px, py));
        let particle = smoothstep(0.005, 0.0, dist) * (1.0 - fall_progress);

        intensity += particle;
    }

    return intensity;
}

// Rez-in: scan line building from bottom
fn rez_in_mask(uv: vec2<f32>, progress: f32, time: f32) -> f32 {
    // Build from bottom to top
    let build_line = progress;
    let visible = step(1.0 - uv.y, build_line);

    // Scan line glow at the build edge
    let edge_dist = abs((1.0 - uv.y) - build_line);
    let scan_line = exp(-edge_dist * 50.0) * 2.0;

    // Horizontal scan segments
    let seg = step(0.3, fract(uv.x * 20.0 + time * 5.0));

    return visible + scan_line * seg;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let uv = in.uv;
    let time = u.time;
    let progress = u.progress;

    let source = textureSample(source_texture, source_sampler, uv);

    if u.direction == 0u {
        // DEREZZ - dissolve into particles
        let mask = particle_mask(uv, progress, time);
        let particles = falling_particles(uv, progress, time);

        let result = source * mask;
        let particle_color = vec4<f32>(u.primary_color.rgb * particles, particles);

        return result + particle_color;
    } else {
        // REZ-IN - materialize from scan lines
        let mask = rez_in_mask(uv, progress, time);

        let visible_part = source * clamp(mask, 0.0, 1.0);
        let scan_glow = vec4<f32>(u.primary_color.rgb * max(mask - 1.0, 0.0), max(mask - 1.0, 0.0));

        return visible_part + scan_glow;
    }
}
