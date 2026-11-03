import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SettingsPanel } from './SettingsPanel';
import { STANDARD_SETTINGS, TWO_PLAYER_SETTINGS } from '../utils/settings';
import type { GameSettings } from '../types/game';

// No DOM in the test setup: the panel is rendered to markup and checked as text.
const render = (settings: GameSettings, editable: boolean) =>
    renderToStaticMarkup(<SettingsPanel settings={settings} editable={editable} send={() => {}} />);

const chip = (markup: string, label: string) => markup.match(new RegExp(`<button[^>]*>${label}</button>`))?.[0] ?? '';

describe('SettingsPanel', () => {
    it('lets the host edit every setting', () => {
        const markup = render(STANDARD_SETTINGS, true);

        expect(markup.match(/<select/g)).toHaveLength(4);
        expect(markup).toContain('type="checkbox"');
        expect(markup).toContain('not enforced yet');
        expect(chip(markup, 'Recommended for 2 players')).not.toContain('disabled');
    });

    it('shows guests the settings read-only', () => {
        const markup = render(TWO_PLAYER_SETTINGS, false);

        expect(markup).not.toContain('<select');
        expect(markup).not.toContain('<input');
        expect(markup).toContain('<dd>8</dd>');
        expect(markup).toContain('<dd>9 cards</dd>');
        expect(chip(markup, 'Recommended for 2 players')).toContain('disabled');
    });

    it('marks the preset that matches the current settings', () => {
        const standard = render(STANDARD_SETTINGS, true);
        expect(chip(standard, 'Standard rules')).toContain('aria-pressed="true"');
        expect(chip(standard, 'Recommended for 2 players')).toContain('aria-pressed="false"');

        const custom = render({ ...TWO_PLAYER_SETTINGS, victory_points: 12 }, true);
        expect(custom).not.toContain('aria-pressed="true"');
    });
});
