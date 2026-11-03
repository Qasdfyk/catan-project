const PIPS: Record<number, [number, number][]> = {
    1: [[12, 12]],
    2: [[6, 6], [18, 18]],
    3: [[6, 6], [12, 12], [18, 18]],
    4: [[6, 6], [18, 6], [6, 18], [18, 18]],
    5: [[6, 6], [18, 6], [12, 12], [6, 18], [18, 18]],
    6: [[6, 6], [18, 6], [6, 12], [18, 12], [6, 18], [18, 18]],
};

const Die = ({ value }: { value: number }) => (
    <svg className="die" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="1" y="1" width="22" height="22" rx="4" />
        {PIPS[value].map(([x, y]) => <circle key={`${x}-${y}`} cx={x} cy={y} r="2.1" />)}
    </svg>
);

interface DiceProps {
    values: number[];
    total: number;
}

// The dice disappear between turns, so every roll mounts them anew and animates.
export const Dice = ({ values, total }: DiceProps) => (
    <span className="dice">
        {values.map((value, index) => <Die key={index} value={value} />)}
        <span data-testid="dice">Rolled {total}</span>
    </span>
);
