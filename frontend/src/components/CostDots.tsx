import type { Cards, Resource } from '../types/game';
import { RESOURCE_COLORS } from '../utils/hexLayout';

export const CostDots = ({ cost }: { cost: Cards }) => (
    <span className="cost" aria-hidden="true">
        {Object.entries(cost).flatMap(([resource, amount]) =>
            Array.from({ length: amount ?? 0 }, (_, index) => (
                <i key={`${resource}-${index}`} style={{ background: RESOURCE_COLORS[resource as Resource] }} />
            )),
        )}
    </span>
);
