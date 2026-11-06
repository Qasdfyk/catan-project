import { RESOURCES, type Cards } from '../types/game';
import { RESOURCE_COLORS } from '../utils/hexLayout';
import { RESOURCE_LABELS } from '../utils/labels';

/** What the own hand got from the last roll, e.g. "+1 Wood +2 Ore". */
export const RollGains = ({ gains }: { gains: Cards }) => {
    const gained = RESOURCES.filter((resource) => (gains[resource] ?? 0) > 0);
    if (gained.length === 0) return null;

    return (
        <p className="roll-gains" role="status" data-testid="roll-gains">
            {gained.map((resource) => (
                <span key={resource} className="roll-gain" style={{ borderColor: RESOURCE_COLORS[resource] }}>
                    +{gains[resource]} {RESOURCE_LABELS[resource]}
                </span>
            ))}
        </p>
    );
};

/** The cards a player got from the last roll, next to their card count. */
export const CardGainBadge = ({ gain }: { gain: number | undefined }) => {
    if (!gain) return null;
    return (
        <span className="gain-badge" title={`Got ${gain} ${gain === 1 ? 'card' : 'cards'} from the roll`}>
            +{gain}
        </span>
    );
};
