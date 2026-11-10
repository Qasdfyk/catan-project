import { memo, type ReactElement } from 'react';
import type { Resource, TileResource } from '../types/game';
import { HEX_SIZE } from '../utils/hexLayout';
import './art.css';

/*
 * Hand-drawn terrain art for the board, in tile coordinates (a pointy-top hex
 * of radius HEX_SIZE around 0,0; the number token covers the middle).
 *
 * Every scene is drawn once inside <ArtDefs> and each tile shows it with a
 * <use>, so a tile adds only a few elements to the DOM however rich the art.
 * Shapes of one colour are merged into one <path> with many sub-paths.
 */

const round = (n: number) => Math.round(n * 10) / 10;
const rad = (deg: number) => (deg * Math.PI) / 180;

/** An ellipse as a sub-path; the long axis `ry` points `deg` degrees clockwise from up. */
const ellipse = (cx: number, cy: number, rx: number, ry: number, deg = 0) => {
    const dx = Math.sin(rad(deg)) * ry;
    const dy = -Math.cos(rad(deg)) * ry;
    const a = `${round(cx + dx)} ${round(cy + dy)}`;
    const b = `${round(cx - dx)} ${round(cy - dy)}`;
    return `M${a}A${rx} ${ry} ${deg} 0 1 ${b}A${rx} ${ry} ${deg} 0 1 ${a}Z`;
};

const circle = (cx: number, cy: number, r: number) =>
    `M${round(cx - r)} ${round(cy)}a${r} ${r} 0 1 0 ${round(2 * r)} 0a${r} ${r} 0 1 0 ${round(-2 * r)} 0Z`;

const polygon = (...pts: number[]) => {
    let d = `M${pts[0]} ${pts[1]}`;
    for (let i = 2; i < pts.length; i += 2) d += `L${pts[i]} ${pts[i + 1]}`;
    return `${d}Z`;
};

/** A four-pointed glint. */
const sparkle = (x: number, y: number, r: number) =>
    `M${x} ${y - r}Q${x} ${y} ${x + r} ${y}Q${x} ${y} ${x} ${y + r}Q${x} ${y} ${x - r} ${y}Q${x} ${y} ${x} ${y - r}Z`;

const hexPoints = (scale: number) => [0, 1, 2, 3, 4, 5]
    .map((i) => {
        const a = rad(60 * i - 30);
        return `${round(HEX_SIZE * scale * Math.cos(a))},${round(HEX_SIZE * scale * Math.sin(a))}`;
    })
    .join(' ');

/** Corners 3, 4, 5, 0 (the edges facing the light) or 0, 1, 2, 3 (the shaded ones). */
const hexEdge = (scale: number, from: number) => [0, 1, 2, 3]
    .map((k) => {
        const a = rad(60 * ((from + k) % 6) - 30);
        return `${round(HEX_SIZE * scale * Math.cos(a))},${round(HEX_SIZE * scale * Math.sin(a))}`;
    })
    .join(' ');

/* ---------- Wheat ---------- */

/** A wheat ear growing from x,y, tilted `tilt` degrees: grains in pairs and one on top. */
const wheatEar = (x: number, y: number, tilt: number, size = 1) => {
    const ux = Math.sin(rad(tilt));
    const uy = -Math.cos(rad(tilt));
    let grains = '';
    let awns = '';
    for (let i = 0; i < 4; i += 1) {
        const s = (1.8 + i * 2.9) * size;
        const cx = x + ux * s;
        const cy = y + uy * s;
        for (const side of [-1, 1]) {
            const gx = cx - uy * 1.5 * size * side;
            const gy = cy + ux * 1.5 * size * side;
            grains += ellipse(gx, gy, 1.3 * size, 2.7 * size, tilt + 24 * side);
            if (i >= 2) {
                const a = rad(tilt + 20 * side);
                awns += `M${round(gx)} ${round(gy)}l${round(Math.sin(a) * 6 * size)} ${round(-Math.cos(a) * 6 * size)}`;
            }
        }
    }
    const tx = x + ux * 13.4 * size;
    const ty = y + uy * 13.4 * size;
    grains += ellipse(tx, ty, 1.2 * size, 2.6 * size, tilt);
    awns += `M${round(tx)} ${round(ty)}l${round(ux * 6 * size)} ${round(uy * 6 * size)}`;
    return { grains, awns };
};

// Ear base x, y, tilt; the stalk runs down to the ground.
const FIELD_EARS: [number, number, number][] = [
    [-28, -30, -8], [-16, -35, 5], [-3, -37, -5], [10, -36, 7], [22, -31, -6],
    [41, -8, 9], [43, 8, -5],
    [-30, 31, -10], [-19, 34, 6], [-8, 37, -4], [3, 38, 8], [14, 36, -6], [25, 33, 10], [35, 28, -8],
];
const SHEAF_EARS: [number, number, number][] = [
    [-43, -3, -30], [-40, -6, -15], [-37, -7, 0], [-34, -6, 14], [-31, -3, 28],
];

const WHEAT = (() => {
    let grains = '';
    let awns = '';
    let stalks = '';
    for (const [x, y, t] of FIELD_EARS) {
        const ear = wheatEar(x, y, t);
        grains += ear.grains;
        awns += ear.awns;
        stalks += `M${x - t * 0.15} ${y + 18}Q${x - t * 0.05} ${y + 8} ${x} ${y}`;
    }
    SHEAF_EARS.forEach(([x, y, t], i) => {
        const ear = wheatEar(x, y, t, 1.05);
        grains += ear.grains;
        awns += ear.awns;
        stalks += `M${x} ${y}Q-37 9 ${-42 + i * 2.5} 22`;
    });
    let furrows = '';
    let ridges = '';
    for (let y = -56; y <= 60; y += 9) {
        furrows += `M-60 ${y}Q0 ${y + 6} 60 ${y}`;
        ridges += `M-60 ${y - 3}Q0 ${y + 3} 60 ${y - 3}`;
    }
    return { grains, awns, stalks, furrows, ridges };
})();

const WheatScene = () => (
    <g id="art-scene-wheat" clipPath="url(#art-hex)">
        <path d={WHEAT.furrows} fill="none" stroke="#b8801e" strokeOpacity={0.35} strokeWidth={3} />
        <path d={WHEAT.ridges} fill="none" stroke="#fff0b0" strokeOpacity={0.5} strokeWidth={1.2} />
        <ellipse cx={-36} cy={22} rx={11} ry={2.8} fill="#7a4f0e" opacity={0.3} />
        <path d={WHEAT.stalks} fill="none" stroke="#a87a22" strokeWidth={1.1} strokeLinecap="round" />
        <path d={WHEAT.awns} fill="none" stroke="#b98a2c" strokeWidth={0.5} strokeLinecap="round" />
        <path d={WHEAT.grains} fill="#f4c94e" stroke="#94631a" strokeWidth={0.55} />
        <path d="M-41.5 8.5Q-37 6.5 -32.5 8.5L-32.5 11Q-37 9 -41.5 11Z" fill="#8a5a17" />
    </g>
);

/* ---------- Pasture ---------- */

const SHEEP_BODY = [
    circle(-6.5, 0, 5), circle(-2.5, -3.5, 5), circle(3, -3.5, 5), circle(6.5, 0, 4.5),
    circle(3, 2.5, 4.5), circle(-2.5, 2.5, 4.5), circle(0, 0, 5), circle(9, -5, 2.4),
].join('');

/** A sheep facing right, its feet on y = 10.5. */
const Sheep = ({ id }: { id?: string }) => (
    <g id={id}>
        <ellipse cx={0.5} cy={10.6} rx={11} ry={2.4} fill="#1f3a10" opacity={0.25} />
        <path d="M-5.5 5v5.2M-1.8 6v4.8M2.4 6v4.8M6 5v5.2" stroke="#2f2826" strokeWidth={1.9} strokeLinecap="round" />
        <path d={SHEEP_BODY} fill="#f3f0e6" stroke="#8f8774" strokeWidth={1.6} paintOrder="stroke" />
        <path d={circle(-3, -5, 2.6) + circle(2.5, -5.5, 2.4) + circle(-7.5, -2, 1.8)} fill="#ffffff" opacity={0.85} />
        <path d={ellipse(11.8, -1.5, 3, 4.4, 125)} fill="#3a3230" />
        <path d={ellipse(9.6, -4.9, 1.1, 2.6, -70)} fill="#2a2321" />
        <path d={circle(13.2, -2.6, 0.6)} fill="#f3f0e6" />
    </g>
);

const GRASS_TUFTS: [number, number][] = [
    [-40, -16], [-14, -46], [14, -44], [36, -26], [-44, 8], [44, 8], [-6, 30], [20, 44],
    [-36, 44], [30, 2], [-24, -2], [8, -28], [-22, 48], [44, -10], [-46, -26],
];
const FLOWERS: [number, number][] = [[-30, -10], [24, -36], [40, 16], [-10, 44], [-42, 22], [10, 52], [-18, -38]];

const PASTURE = {
    tufts: GRASS_TUFTS.map(([x, y]) => `M${x} ${y}l-3 -5M${x} ${y}l0 -6M${x} ${y}l3 -5`).join(''),
    petals: FLOWERS.map(([x, y]) => circle(x, y, 1.6)).join(''),
    hearts: FLOWERS.map(([x, y]) => circle(x, y, 0.7)).join(''),
    patches: ellipse(-24, -26, 14, 22, 70) + ellipse(26, 30, 12, 20, 60) + ellipse(30, -18, 9, 14, 100),
};

const PastureScene = () => (
    <g id="art-scene-sheep" clipPath="url(#art-hex)">
        <path d={PASTURE.patches} fill="#d4f0a0" opacity={0.45} />
        <path d={PASTURE.tufts} fill="none" stroke="#4f8a2e" strokeWidth={1.4} strokeLinecap="round" />
        <path d={PASTURE.petals} fill="#ffffff" />
        <path d={PASTURE.hearts} fill="#f2c230" />
        <path d="M-60 40Q-46 34 -38 44L-30 60H-60Z" fill="#6aa43c" opacity={0.6} />
        <use href="#art-sheep" transform="translate(-26 -22) scale(1.05)" />
        <use href="#art-sheep" transform="translate(32 -6) scale(-0.95 0.95)" />
        <use href="#art-sheep" transform="translate(16 34) scale(1.15)" />
        <use href="#art-sheep" transform="translate(-28 28) scale(-0.9 0.9)" />
    </g>
);

/* ---------- Forest ---------- */

/** A pine standing on 0,0; the crown takes the colour of the <use>. */
const Pine = () => (
    <g id="art-pine">
        <ellipse cx={3} cy={0} rx={9.5} ry={2.6} fill="#0f2a12" opacity={0.4} />
        <rect x={-1.8} y={-6} width={3.6} height={6.5} fill="#6e4526" />
        <path d="M0 -31L7 -20H4.5L10 -12H7L12 -4H-12L-7 -12H-10L-4.5 -20H-7Z" />
        <path d="M0 -31L7 -20H4.5L10 -12H7L12 -4H0Z" fill="#001a08" opacity={0.3} />
        <path d="M0 -31L-7 -20H-4.5ZM-4.5 -20L-10 -12H-7ZM-7 -12L-12 -4H-9Z" fill="#e8ffc0" opacity={0.25} />
    </g>
);

const OAK_CROWN = [circle(0, -18, 8), circle(-6, -14, 6), circle(6, -14, 6), circle(-3, -22, 6), circle(4, -22, 6)].join('');

/** A leafy tree standing on 0,0; the crown takes the colour of the <use>. */
const Oak = () => (
    <g id="art-oak">
        <ellipse cx={3} cy={0} rx={10} ry={2.8} fill="#0f2a12" opacity={0.4} />
        <path d="M-2 0.5L-1.4 -10H1.4L2 0.5Z" fill="#6e4526" />
        <path d={OAK_CROWN} />
        <path d={circle(3.5, -13.5, 4.5) + circle(6.5, -16, 3.5)} fill="#001a08" opacity={0.25} />
        <path d={circle(-4, -20, 3) + circle(-0.5, -23.5, 2.4)} fill="#f4ffc8" opacity={0.25} />
    </g>
);

// Base x, y, kind, scale, crown colour; drawn back (top) to front (bottom).
const TREES: [number, number, 'pine' | 'oak', number, string][] = [
    [12, -42, 'pine', 0.6, '#2f7a44'],
    [-10, -40, 'pine', 0.6, '#3a8a4a'],
    [-36, -24, 'oak', 0.8, '#5aa646'],
    [0, -27, 'oak', 0.75, '#4f9a3e'],
    [24, -26, 'pine', 0.85, '#276b3c'],
    [-24, -22, 'pine', 0.85, '#2f7a44'],
    [-40, 0, 'pine', 0.85, '#276b3c'],
    [40, 0, 'oak', 0.85, '#5aa646'],
    [-30, 24, 'oak', 0.85, '#4f9a3e'],
    [30, 25, 'pine', 0.95, '#2f7a44'],
    [-14, 45, 'pine', 1, '#3a8a4a'],
    [14, 47, 'pine', 0.95, '#276b3c'],
];

const ForestScene = () => (
    <g id="art-scene-wood" clipPath="url(#art-hex)">
        <path d={ellipse(0, 0, 24, 28, 90)} fill="#a9cc6e" opacity={0.35} />
        <path d={ellipse(-30, -40, 6, 20, 70) + ellipse(34, 40, 6, 18, 110)} fill="#173d1c" opacity={0.3} />
        {TREES.map(([x, y, kind, scale, fill]) => (
            <use key={`${x},${y}`} href={`#art-${kind}`} fill={fill} transform={`translate(${x} ${y}) scale(${scale})`} />
        ))}
    </g>
);

/* ---------- Hills (brick) ---------- */

/** A brick seen from the front-right: front, top and side faces. */
const brick = (x: number, y: number, w: number, h: number, depth = 3) => ({
    front: `M${x} ${y}h${w}v${h}h${-w}Z`,
    top: `M${x} ${y}l${depth} ${-depth}h${w}l${-depth} ${depth}Z`,
    side: `M${x + w} ${y}l${depth} ${-depth}v${h}l${-depth} ${depth}Z`,
});

const BRICK_PILE = (() => {
    const bricks = [brick(4, 36, 11, 5.5, 2.5), brick(16, 36, 11, 5.5, 2.5), brick(10, 30.5, 11, 5.5, 2.5)];
    return {
        front: bricks.map((b) => b.front).join(''),
        top: bricks.map((b) => b.top).join(''),
        side: bricks.map((b) => b.side).join(''),
    };
})();

const WALL_BRICKS = (() => {
    const rows = [-7.4, -2.2, 3, 8.2];
    let d = '';
    rows.forEach((y, row) => {
        const starts = row % 2 === 0 ? [22.6, 31, 39.4] : [22.6, 26.8, 35.2, 43.6];
        for (const x of starts) {
            const end = Math.min(x + 7.6, 47.4);
            const width = row % 2 === 1 && x === 22.6 ? 3.4 : end - x;
            d += `M${x} ${y}h${round(width)}v4.4h${round(-width)}Z`;
        }
    });
    return d;
})();

const HillsScene = () => (
    <g id="art-scene-brick" clipPath="url(#art-hex)">
        <path d="M-8 -12C-2 -50 46 -56 62 -16ZM-62 4C-56 -34 -8 -46 4 -10Z" fill="#d77d4c" />
        <path d="M30 -46C46 -44 56 -32 62 -16C48 -26 42 -36 30 -46ZM-24 -37C-8 -38 2 -24 4 -10C-8 -18 -14 -28 -24 -37Z" fill="#8f3a1c" opacity={0.35} />
        <path d="M-2 -24C4 -40 16 -46 26 -47M-54 -10C-48 -28 -36 -36 -26 -37" fill="none" stroke="#f6bd93" strokeWidth={2} strokeLinecap="round" />
        <path d="M-46 -12C-36 -24 -20 -26 -8 -18M6 -26C16 -36 32 -38 46 -28" fill="none" stroke="#9a4524" strokeOpacity={0.45} strokeWidth={1.2} strokeLinecap="round" />
        <path d="M-50 4l6 -2l3 3M-14 -46l5 1M40 32l5 -2l2 3M-6 52l6 -1M-48 -18l4 2" fill="none" stroke="#6e2a12" strokeOpacity={0.45} strokeWidth={1.2} strokeLinecap="round" />
        <ellipse cx={-27} cy={33} rx={15} ry={7.5} fill="#eaa070" />
        <ellipse cx={-27} cy={34} rx={12} ry={5.6} fill="#6a2814" />
        <ellipse cx={-25.5} cy={35.6} rx={7.5} ry={2.6} fill="#9c4526" />
        <path d="M22 13L48 13L54 17L28 17ZM4 41.5H27L31 44.5H8Z" fill="#3a1408" opacity={0.25} />
        <rect x={22} y={-8} width={26} height={21} fill="#ead3b0" />
        <path d={WALL_BRICKS} fill="#b5452a" />
        <path d="M22 -8L25 -11H51L48 -8Z" fill="#dd8a62" />
        <path d="M48 -8L51 -11V10L48 13Z" fill="#7f2f17" />
        <path d={BRICK_PILE.top} fill="#e08d64" />
        <path d={BRICK_PILE.side} fill="#842f17" />
        <path d={BRICK_PILE.front} fill="#b5452a" stroke="#7a2a12" strokeWidth={0.6} />
    </g>
);

/* ---------- Mountains (ore) ---------- */

/** A mountain with a lit west face, a shaded east face and snow down to `snow` of its height. */
const mountain = (px: number, py: number, left: number, right: number, base: number, snow = 0.26) => {
    const kink = { x: px + (right - px) * 0.18, y: py + (base - py) * 0.45 };
    const foot = { x: px + (right - px) * 0.3, y: base };
    const at = (x: number, y: number, f: number) => [round(px + (x - px) * f), round(py + (y - py) * f)];
    const [llx, lly] = at(left, base, snow);
    const [rx, ry] = at(right, base, snow);
    const [kx, ky] = at(kink.x, kink.y, snow / 0.45);
    const [mx, my] = at((left + kink.x) / 2, base, snow * 0.8);
    const [nx, ny] = at((left + kink.x) / 2 - 6, base, snow * 1.15);
    const [sx, sy] = at((right + kink.x) / 2, base, snow * 1.2);
    return {
        lit: polygon(left, base, px, py, kink.x, kink.y, foot.x, foot.y),
        shade: polygon(px, py, right, base, foot.x, foot.y, kink.x, kink.y),
        snowLit: polygon(px, py, llx, lly, nx, ny, mx, my, kx, ky),
        snowShade: polygon(px, py, kx, ky, sx, sy, rx, ry),
    };
};

// Back to front.
const MOUNTAINS = [
    mountain(20, -52, -18, 62, 6),
    mountain(-22, -44, -62, 16, 4),
    mountain(-33, 12, -62, -4, 50, 0.3),
    mountain(33, 8, 2, 62, 46, 0.3),
];

const ORE = {
    rockLit: polygon(-14, 56, -9, 44, 0, 40, 8, 46, 6, 58) + polygon(-50, -8, -45, -16, -38, -12, -40, -5),
    rockShade: polygon(0, 40, 8, 46, 6, 58, 1, 55, 2, 47) + polygon(-38, -12, -40, -5, -44, -7),
    veins: polygon(-6, 50, -3, 47, 0, 50, -3, 53) + polygon(-30, 30, -27, 27, -24, 30, -27, 33)
        + polygon(36, 26, 39, 23, 42, 26, 39, 29) + polygon(-26, -18, -23, -21, -20, -18, -23, -15)
        + polygon(26, -24, 29, -27, 32, -24, 29, -21),
    glints: sparkle(-1, 43.5, 3.5) + sparkle(-25, 26, 3.5) + sparkle(41, 22, 3.5) + sparkle(-21, -22, 3)
        + sparkle(31, -28, 3) + sparkle(-46, -15, 2.5),
    cracks: 'M-34 -14l5 5l-1 6M42 -20l-4 6M-42 34l5 3M22 30l4 5M10 -38l3 6',
};

const MountainsScene = () => (
    <g id="art-scene-ore" clipPath="url(#art-hex)">
        {MOUNTAINS.map((m, i) => (
            <g key={i}>
                <path d={m.lit} fill="#a9b2bc" />
                <path d={m.shade} fill="#67707b" />
                <path d={m.snowLit} fill="#ffffff" />
                <path d={m.snowShade} fill="#c6d1dd" />
            </g>
        ))}
        <path d={ORE.cracks} fill="none" stroke="#3e4550" strokeOpacity={0.5} strokeWidth={1} strokeLinecap="round" />
        <path d={ORE.rockLit} fill="#8d96a1" stroke="#454c56" strokeWidth={0.7} strokeLinejoin="round" />
        <path d={ORE.rockShade} fill="#5a626d" />
        <path d={ORE.veins} fill="#3b5f8c" stroke="#a9c9ef" strokeWidth={0.6} />
        <path d={ORE.glints} fill="#fff4b8" />
    </g>
);

/* ---------- Desert ---------- */

const DUNES = [
    ['M-60 -30Q-24 -52 14 -34', 'Q-22 -40 -60 -18'],
    ['M4 -20Q34 -42 60 -22', 'Q34 -30 4 -14'],
    ['M-60 18Q-30 2 -2 24', 'Q-28 12 -60 30'],
    ['M6 34Q32 14 60 28', 'Q32 24 6 42'],
];

const DESERT = {
    shade: DUNES.map(([crest, back]) => `${crest}${back}Z`).join(''),
    crests: DUNES.map(([crest]) => crest).join(''),
    ripples: 'M-40 -4q6 -3 12 0t12 0M-48 46q6 -3 12 0t12 0M22 2q5 -3 10 0t10 0M-14 -46q5 -3 10 0t10 0M28 52q4 -2 8 0',
    pebbles: ellipse(-36, 40, 2.6, 3.6, 70) + ellipse(-30, 43, 1.8, 2.4, 100) + ellipse(40, -40, 2.2, 3, 80)
        + ellipse(-6, 52, 2, 2.8, 60) + ellipse(44, 46, 1.6, 2.2, 90) + ellipse(-44, -6, 2, 2.6, 110),
    bush: 'M36 8L33 -2L29 -8M33 -2L35 -10M36 8L38 -3L42 -9M38 -3L36 -12M36 8L42 1L47 -2M36 8L30 3L25 2'
        + 'M-22 -24L-24 -30L-28 -33M-24 -30L-22 -36M-22 -24L-19 -31L-16 -33M-22 -24L-27 -26',
};

const DesertScene = () => (
    <g id="art-scene-desert" clipPath="url(#art-hex)">
        <path d={DESERT.shade} fill="#b07f3c" opacity={0.42} />
        <path d={DESERT.crests} fill="none" stroke="#fff6da" strokeWidth={1.6} strokeLinecap="round" />
        <path d={DESERT.ripples} fill="none" stroke="#a47a3c" strokeOpacity={0.4} strokeWidth={0.9} strokeLinecap="round" />
        <path d={ellipse(37, 8.5, 2.2, 9, 90) + ellipse(-21, -23.5, 1.6, 6, 90)} fill="#6b4a1e" opacity={0.25} />
        <path d={DESERT.bush} fill="none" stroke="#7a5532" strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
        <path d={DESERT.pebbles} fill="#a8875a" stroke="#6f5532" strokeWidth={0.5} />
    </g>
);

/* ---------- Shared definitions ---------- */

const GROUNDS: Record<TileResource, [string, string, string]> = {
    wheat: ['#fbe08a', '#e9b944', '#c98f22'],
    sheep: ['#c8ea8e', '#98cb62', '#6fa845'],
    wood: ['#6aa452', '#3f7a3a', '#285427'],
    brick: ['#e0956a', '#bf5f36', '#8f3d20'],
    ore: ['#bfc6ce', '#8c95a0', '#5c646e'],
    desert: ['#f8eac0', '#ead08f', '#cfa865'],
};

const ArtDefsInner = () => (
    <defs>
        <clipPath id="art-hex">
            <polygon points={hexPoints(1)} />
        </clipPath>
        {Object.entries(GROUNDS).map(([resource, [light, mid, dark]]) => (
            <radialGradient key={resource} id={`art-ground-${resource}`} cx="0.36" cy="0.3" r="0.85">
                <stop offset="0" stopColor={light} />
                <stop offset="0.55" stopColor={mid} />
                <stop offset="1" stopColor={dark} />
            </radialGradient>
        ))}
        <radialGradient id="art-token" cx="0.4" cy="0.35" r="0.7">
            <stop offset="0" stopColor="#fffcf2" />
            <stop offset="0.7" stopColor="#f6ecd2" />
            <stop offset="1" stopColor="#e2d0a8" />
        </radialGradient>
        <radialGradient id="art-sea-shallow" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0.75" stopColor="#7fd0e6" stopOpacity="0.5" />
            <stop offset="1" stopColor="#7fd0e6" stopOpacity="0" />
        </radialGradient>
        <Sheep id="art-sheep" />
        <Pine />
        <Oak />
        <WheatScene />
        <PastureScene />
        <ForestScene />
        <HillsScene />
        <MountainsScene />
        <DesertScene />
        <g id="art-bevel" fill="none" pointerEvents="none">
            <polyline points={hexEdge(0.93, 3)} stroke="#fffbe8" strokeOpacity={0.45} strokeWidth={2.2} strokeLinejoin="round" />
            <polyline points={hexEdge(0.93, 0)} stroke="#2a1806" strokeOpacity={0.28} strokeWidth={2.6} strokeLinejoin="round" />
            <polygon points={hexPoints(0.975)} stroke="#4a3010" strokeOpacity={0.35} strokeWidth={1.2} />
            <polygon points={hexPoints(1)} stroke="#f4e7c6" strokeWidth={2.4} strokeLinejoin="round" />
        </g>
    </defs>
);

/** The gradients, clip path and terrain scenes; render once inside the board <svg>. */
export const ArtDefs = memo(ArtDefsInner);

/** The illustration and cardboard edge of one tile, placed at its centre. */
export const TileArt = memo(({ resource, x, y, rolled }: {
    resource: TileResource;
    x: number;
    y: number;
    rolled: boolean;
}) => (
    <>
        <use
            className={rolled ? 'art-scene rolled' : 'art-scene'}
            href={`#art-scene-${resource}`}
            transform={`translate(${round(x)} ${round(y)})`}
        />
        <use href="#art-bevel" transform={`translate(${round(x)} ${round(y)})`} />
    </>
));

/* ---------- Resource icons ---------- */

const OUTLINE = '#4a3320';

const ICON_WHEAT = (() => {
    const ear = wheatEar(18, 20.5, 14, 1.05);
    return { grains: ear.grains, awns: ear.awns };
})();

const ICON_BRICKS = [brick(3, 19, 12, 8), brick(16, 19, 12, 8), brick(9.5, 11, 12, 8)];

const ICON_ART: Record<Resource, ReactElement> = {
    wood: (
        <>
            <rect x={14.3} y={23} width={3.4} height={6} fill="#7a4a26" stroke={OUTLINE} strokeWidth={1} />
            <path d="M16 2.5L22 10.5H19L24 17.5H20.5L26 25H6L11.5 17.5H8L13 10.5H10Z" fill="#3f8f4e" stroke={OUTLINE} strokeWidth={1.2} strokeLinejoin="round" />
            <path d="M16 3.5L21.3 10.5H19L24 17.5H20.5L25.3 24.4H16Z" fill="#00200a" opacity={0.25} />
            <path d="M16 3.5L11 10.2H13ZM12.6 10.5L8.6 17.2H11ZM11.3 17.5L6.8 24.4H9.6Z" fill="#e8ffc0" opacity={0.4} />
        </>
    ),
    brick: (
        <>
            {ICON_BRICKS.map((b, i) => (
                <g key={i} stroke={OUTLINE} strokeWidth={1} strokeLinejoin="round">
                    <path d={b.top} fill="#e08d64" />
                    <path d={b.side} fill="#842f17" />
                    <path d={b.front} fill="#b5452a" />
                </g>
            ))}
        </>
    ),
    sheep: (
        <g transform="translate(13.6 14.6) scale(1.04)">
            <path d="M-5.5 5v5.2M-1.8 6v4.8M2.4 6v4.8M6 5v5.2" stroke="#2f2826" strokeWidth={2.1} strokeLinecap="round" />
            <path d={SHEEP_BODY} fill="#f6f3ea" stroke={OUTLINE} strokeWidth={2} paintOrder="stroke" />
            <path d={circle(-3, -5, 2.6) + circle(2.5, -5.5, 2.4)} fill="#ffffff" />
            <path d={ellipse(11.8, -1.5, 3, 4.4, 125)} fill="#3a3230" />
            <path d={ellipse(9.6, -4.9, 1.1, 2.6, -70)} fill="#2a2321" />
        </g>
    ),
    wheat: (
        <>
            <path d="M11.5 30.5Q15 25.5 18 20.5" fill="none" stroke="#9a6b17" strokeWidth={1.6} strokeLinecap="round" />
            <path d="M13.6 25.5Q7.5 23 6.5 17Q11.5 19 13.6 25.5Z" fill="#c9a03a" stroke="#8a5f14" strokeWidth={0.8} />
            <path d={ICON_WHEAT.awns} fill="none" stroke="#a87a22" strokeWidth={0.7} strokeLinecap="round" />
            <path d={ICON_WHEAT.grains} fill="#f2c34a" stroke="#7d5410" strokeWidth={0.8} />
        </>
    ),
    ore: (
        <>
            <path d="M4 23L8.5 11L17 5.5L26.5 9.5L29 21L21 27.5H9.5Z" fill="#8d96a1" stroke={OUTLINE} strokeWidth={1.2} strokeLinejoin="round" />
            <path d="M8.5 11L17 5.5L18 14L9 17.5Z" fill="#c3cad2" />
            <path d="M26.5 9.5L29 21L21 27.5L18 14Z" fill="#5a626d" />
            <path d="M11 21l3 -3l3 3l-3 3ZM20 18l2.5 -2.5l2.5 2.5l-2.5 2.5Z" fill="#3b5f8c" stroke="#a9c9ef" strokeWidth={0.6} />
            <path d={sparkle(14, 9.5, 3.4) + sparkle(24.5, 23, 2.6)} fill="#fff1a0" />
        </>
    ),
};

/** The resource art in a 32×32 box, for embedding in another <svg>. */
export const ResourceIconArt = ({ resource }: { resource: Resource }) => ICON_ART[resource];

export const ResourceIcon = ({
    resource,
    size = 28,
    label = false,
}: {
    resource: Resource;
    size?: number;
    /** Give the icon a name for screen readers; by default it is decorative. */
    label?: boolean;
}) => (
    <svg
        className={`resource-icon resource-icon-${resource}`}
        viewBox="0 0 32 32"
        width={size}
        height={size}
        {...(label ? { role: 'img', 'aria-label': resource } : { 'aria-hidden': true })}
    >
        {ICON_ART[resource]}
    </svg>
);
