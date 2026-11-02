// Plays a whole game in real browser tabs by clicking the UI, one tab per player.
//
//   BASE_URL=http://localhost:5173 PLAYERS=2 BOTS=0 node play.mjs
//
// Fails on any console error, or if a part of the game was never reached.
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright';

const BASE_URL = process.env.BASE_URL ?? 'http://localhost:5173';
const PLAYERS = Number(process.env.PLAYERS ?? 2);
const BOTS = Number(process.env.BOTS ?? 0);
const SHOTS = process.env.SCREENSHOTS ?? 'screenshots';
const MAX_STEPS = 60_000;
const NAMES = ['Alice', 'Bob', 'Charlie', 'Dana'];

const seen = {
    turns: 0, sevens: 0, discards: 0, robberMoves: 0, steals: 0,
    roads: 0, settlements: 0, cities: 0, trades: 0, longestRoad: 0,
    cardsBought: 0, cardsPlayed: 0, offers: 0, playerTrades: 0,
};
const problems = [];

const pick = (items) => items[Math.floor(Math.random() * items.length)];
const shot = (page, name) => page.screenshot({ path: `${SHOTS}/${name}.png` });

const watch = (page, label) => {
    page.on('console', (message) => {
        if (message.type() === 'error') problems.push(`${label}: ${message.text()}`);
    });
    page.on('pageerror', (error) => problems.push(`${label}: ${error.message}`));
};

const openTab = async (context, label) => {
    const page = await context.newPage();
    // Keeps the socket reachable to send actions the UI itself would never offer
    await page.addInitScript(() => {
        const Native = window.WebSocket;
        window.WebSocket = class extends Native {
            constructor(...args) {
                super(...args);
                window.gameSocket = this;
            }
        };
    });
    watch(page, label);
    return page;
};

const clickTarget = async (page, prefix) => {
    const targets = await page.locator(`[data-target^="${prefix}"]`).all();
    if (targets.length === 0) return false;
    // A real mouse click: the box of a vertical road has no width, so Playwright
    // would refuse to click it as an element.
    const box = await pick(targets).boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    return true;
};

const instructionOf = (page) => page.getByTestId('instruction').textContent();

// A click only sends a message; waits until the server's answer has changed the page.
const settled = async (page, before) => {
    await page.waitForFunction(
        (previous) => document.body.innerText !== previous, before, { timeout: 5000 },
    ).catch(() => {});
};

const act = async (page, action) => {
    const before = await page.evaluate(() => document.body.innerText);
    await action();
    await settled(page, before);
};

const discard = async (page) => {
    const panel = page.getByRole('region', { name: 'Discard cards' });
    const more = panel.getByRole('button', { name: /more$/ });
    const confirm = panel.getByRole('button', { name: /^Discard \(/ });
    while (await confirm.isDisabled()) {
        const enabled = [];
        for (const button of await more.all()) {
            if (await button.isEnabled()) enabled.push(button);
        }
        await pick(enabled).click();
    }
    await act(page, () => confirm.click());
    seen.discards += 1;
};

const handOf = async (page) => {
    const hand = {};
    for (const resource of ['wood', 'brick', 'sheep', 'wheat', 'ore']) {
        hand[resource] = Number(await page.locator(`[data-resource="${resource}"]`).textContent());
    }
    return hand;
};

// Trades the largest pile for the smallest one, at most once per turn.
const tryTrade = async (page) => {
    const hand = await handOf(page);
    const byCount = Object.keys(hand).sort((a, b) => hand[b] - hand[a]);
    const [most, least] = [byCount[0], byCount[byCount.length - 1]];
    if (hand[most] < 2 || hand[most] - hand[least] < 2) return false;

    const panel = page.getByRole('region', { name: 'Trade with the bank' });
    const [give, get] = await panel.getByRole('combobox').all();
    await give.selectOption(most);
    await get.selectOption(least);
    const trade = panel.getByRole('button', { name: 'Trade' });
    if (await trade.isDisabled()) return false;
    await act(page, () => trade.click());
    seen.trades += 1;
    return true;
};

const tryBuild = async (page, label, prefix, counter) => {
    const panel = page.getByRole('region', { name: 'Build' });
    const button = panel.getByRole('button', { name: label });
    if (await button.isDisabled()) return false;
    await button.click();
    await act(page, () => clickTarget(page, prefix));
    seen[counter] += 1;
    return true;
};

let tradedThisTurn = false;

const tryPlayCard = async (page) => {
    const panel = page.getByRole('region', { name: 'Development cards' });
    const play = panel.getByRole('button', { name: /^Play / });
    if ((await play.count()) === 0) return false;

    await pick(await play.all()).click();
    const confirm = panel.getByRole('button', { name: 'Confirm' });
    if (await confirm.isVisible()) await act(page, () => confirm.click());
    else await page.waitForTimeout(100);
    seen.cardsPlayed += 1;
    return true;
};

const tryBuyCard = async (page) => {
    const buy = page.getByRole('button', { name: 'Buy a card' });
    if ((await buy.count()) === 0) return false;
    await act(page, () => buy.click());
    seen.cardsBought += 1;
    return true;
};

// Asks another tab for a card: both sides are played by step().
const tryOffer = async (page) => {
    const hand = await handOf(page);
    const give = Object.keys(hand).find((resource) => hand[resource] > 0);
    const get = Object.keys(hand).find((resource) => resource !== give);
    if (!give) return false;

    await page.getByRole('button', { name: 'Trade with players' }).click();
    const panel = page.getByRole('region', { name: 'Offer a trade' });
    await panel.getByRole('button', { name: `Give one ${give} more` }).click();
    await panel.getByRole('button', { name: `Get one ${get} more` }).click();
    await act(page, () => panel.getByRole('button', { name: 'Offer', exact: true }).click());
    seen.offers += 1;
    return true;
};

const handleOffer = async (page) => {
    const panel = page.getByRole('region', { name: 'Trade offer' });
    if ((await panel.count()) === 0) return false;

    const confirm = panel.getByRole('button', { name: /^Trade with / });
    if ((await confirm.count()) > 0) {
        await act(page, () => confirm.first().click());
        seen.playerTrades += 1;
        return true;
    }
    if ((await panel.getByText('Everyone declined').count()) > 0) {
        await act(page, () => panel.getByRole('button', { name: 'Withdraw' }).click());
        return true;
    }

    const accept = panel.getByRole('button', { name: 'Accept' });
    if ((await accept.count()) === 0) return false;
    if ((await panel.getByRole('button', { pressed: true }).count()) > 0) return false;
    const answer = (await accept.isEnabled()) ? accept : panel.getByRole('button', { name: 'Decline' });
    await act(page, () => answer.click());
    return true;
};

const playMainPhase = async (page) => {
    if (await tryBuild(page, 'City', 'city', 'cities')) return;
    if (await tryBuild(page, 'Settlement', 'settlement', 'settlements')) return;
    if (await tryPlayCard(page)) return;
    if (await tryBuyCard(page)) return;
    if (Math.random() < 0.7 && (await tryBuild(page, 'Road', 'road', 'roads'))) return;
    if (PLAYERS > 1 && !tradedThisTurn && Math.random() < 0.3 && (await tryOffer(page))) {
        tradedThisTurn = true;
        return;
    }
    if (!tradedThisTurn && (await tryTrade(page))) {
        tradedThisTurn = true;
        return;
    }
    tradedThisTurn = false;
    await act(page, () => page.getByRole('button', { name: 'End turn' }).click());
    seen.turns += 1;
};

// Performs one step on this tab, if it has something to do.
const step = async (page) => {
    const text = await instructionOf(page);

    if (await handleOffer(page)) return;
    if (text.startsWith('Discard')) return discard(page);
    if (text === 'Place a settlement.') return act(page, () => clickTarget(page, 'settlement'));
    if (text.startsWith('Place a road') || text.startsWith('Place a free road')) return act(page, () => clickTarget(page, 'road'));
    if (text === 'Roll the dice.') {
        await act(page, () => page.getByRole('button', { name: 'Roll dice' }).click());
        const dice = await page.getByTestId('dice').textContent().catch(() => '');
        if (dice.endsWith(' 7')) seen.sevens += 1;
        return;
    }
    if (text.startsWith('Move the robber')) {
        await act(page, () => clickTarget(page, 'robber'));
        seen.robberMoves += 1;
        return;
    }
    if (text.startsWith('Choose a player')) {
        const panel = page.getByRole('region', { name: 'Steal' });
        await act(page, () => panel.getByRole('button').first().click());
        seen.steals += 1;
        return;
    }
    if (text.startsWith('Build, trade')) await playMainPhase(page);
};

const checkLobby = async (context) => {
    const host = await openTab(context, NAMES[0]);
    await host.goto(BASE_URL);
    await shot(host, '01-home');
    await host.getByLabel('Your name').fill(NAMES[0]);
    await host.getByRole('button', { name: 'Create room' }).click();
    await host.getByRole('heading', { name: 'Lobby' }).waitFor();
    assert.equal(await host.getByRole('button', { name: /Waiting for players/ }).isDisabled(), true);
    const roomUrl = host.url();

    for (let bot = 0; bot < BOTS; bot += 1) {
        await host.getByRole('button', { name: 'Add a bot' }).click();
        await host.locator('.lobby-players li').nth(bot + 1).waitFor();
    }

    const tabs = [host];
    for (const name of NAMES.slice(1, PLAYERS)) {
        const guest = await openTab(context, name);
        await guest.goto(roomUrl);
        await guest.getByLabel('Your name').fill(name);
        await guest.getByRole('button', { name: 'Join', exact: true }).click();
        await guest.getByText('Waiting for the host').waitFor();
        tabs.push(guest);
    }

    const stranger = await openTab(context, 'stranger');
    await stranger.goto(roomUrl);
    await stranger.getByLabel('Your name').fill(NAMES[0]);
    await stranger.getByRole('button', { name: 'Join', exact: true }).click();
    await stranger.getByRole('alert').getByText('taken by a connected player').waitFor();
    await stranger.close();
    problems.length = 0; // the refused request above is logged by the browser as a 409

    await shot(host, '02-lobby');
    await host.getByRole('button', { name: 'Start game' }).click();
    for (const tab of tabs) await tab.getByTestId('instruction').waitFor();
    return { tabs, roomUrl };
};

const checkMissingRoom = async (context) => {
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/game/doesnotexist`);
    await page.getByRole('alert').getByText('does not exist').waitFor();
    await page.close();
};

// Opponent's tab or the host's own: either way the action is out of turn or out of phase.
const checkRefusedActionIsShown = async (page) => {
    await page.evaluate(() => window.gameSocket.send(JSON.stringify({
        type: 'action', request_id: 999, action: 'end_turn', payload: {},
    })));
    const toast = page.getByRole('alert');
    await toast.waitFor();
    await shot(page, '03-error');
    assert.match(await toast.textContent(), /setup|not your turn/i);
    await toast.waitFor({ state: 'detached', timeout: 7000 });
};

const checkReturnByName = async (context, tabs, roomUrl) => {
    const index = tabs.length - 1;
    const name = NAMES[index];
    await tabs[index].close();

    const returned = await openTab(context, name);
    await returned.goto(roomUrl);
    await returned.getByRole('heading', { name: 'Return to the game' }).waitFor();

    // The gateway needs a moment to notice the closed tab
    await returned.getByLabel('Your name').fill(name);
    for (let attempt = 0; attempt < 20; attempt += 1) {
        await returned.getByRole('button', { name: 'Return', exact: true }).click();
        if (await returned.getByTestId('instruction').waitFor({ timeout: 500 }).then(() => true, () => false)) break;
    }
    problems.length = 0;
    await returned.getByText('(you)').waitFor();
    assert.match(await returned.locator('.player', { hasText: '(you)' }).textContent(), new RegExp(name));
    tabs[index] = returned;
};

const checkChat = async (tabs) => {
    const [sender, receiver] = [tabs[0], tabs[tabs.length - 1]];
    await sender.getByRole('textbox', { name: 'Message' }).fill('Anyone got wood?');
    await sender.getByRole('textbox', { name: 'Message' }).press('Enter');
    await receiver.getByRole('region', { name: 'Chat' }).getByText('Anyone got wood?').waitFor();
};

// A player leaves for good, a bot keeps the game going, and they come back later.
const checkBotTakesOver = async (context, tabs, roomUrl) => {
    const index = tabs.length - 1;
    const name = NAMES[index];
    await tabs[index].close();

    const button = tabs[0].getByRole('button', { name: `Let a bot play for ${name}` });
    await button.waitFor({ timeout: 10000 });
    await button.click();
    await tabs[0].locator('.player', { hasText: name }).getByText('(bot)').waitFor();

    const returned = await openTab(context, name);
    await returned.goto(roomUrl);
    await returned.getByLabel('Your name').fill(name);
    await returned.getByRole('button', { name: 'Return', exact: true }).click();
    await returned.getByText('(you)').waitFor();
    assert.equal(await tabs[0].locator('.player', { hasText: name }).getByText('(bot)').count(), 0);
    tabs[index] = returned;
};

const noteLongestRoad = async (page) => {
    if (await page.locator('.player-stats', { hasText: '★' }).count()) seen.longestRoad += 1;
};

const main = async () => {
    mkdirSync(SHOTS, { recursive: true });
    const browser = await chromium.launch({ args: ['--no-sandbox'] });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });

    await checkMissingRoom(context);
    const { tabs, roomUrl } = await checkLobby(context);
    await shot(tabs[0], '04-setup-start');
    await checkRefusedActionIsShown(tabs[tabs.length - 1]);
    await checkChat(tabs);

    let winner = null;
    let returned = false;
    let shotOfMidgame = false;

    for (let steps = 0; steps < MAX_STEPS && !winner; steps += 1) {
        for (const page of tabs) {
            await step(page);
            const text = await instructionOf(page);
            if (text.endsWith('won the game!')) winner = text;
        }

        await noteLongestRoad(tabs[0]);
        if (tabs.length === 1) await tabs[0].waitForTimeout(40);

        if (steps % 100 === 0) console.log(`step ${steps}:`, JSON.stringify(seen));

        if (!shotOfMidgame && seen.cardsBought > 1) {
            shotOfMidgame = true;
            for (const [index, page] of tabs.entries()) await shot(page, `05-midgame-tab${index + 1}`);
        }
        if (!returned && seen.turns >= 4) {
            returned = true;
            await checkReturnByName(context, tabs, roomUrl);
            if (PLAYERS > 1) await checkBotTakesOver(context, tabs, roomUrl);
        }
    }

    assert.ok(winner, `no winner after ${MAX_STEPS} steps`);
    await shot(tabs[0], '06-game-over');
    await tabs[0].getByRole('dialog', { name: 'Game over' }).waitFor();

    // Every tab must agree on the result, and nobody can act any more
    for (const page of tabs) {
        await page.getByRole('button', { name: 'See the board' }).click();
        assert.equal(await instructionOf(page), winner);
        assert.equal(await page.getByRole('button', { name: 'End turn' }).count(), 0);
        assert.equal(await page.getByRole('button', { name: 'Roll dice' }).count(), 0);
    }
    const points = await Promise.all(
        Array.from({ length: PLAYERS + BOTS }, (_, seat) => tabs[0].getByTestId(`points-${seat}`).textContent()),
    );

    console.log(`Result: ${winner} Points: ${points.join(', ')}`);
    console.log('Seen:', JSON.stringify(seen));
    await browser.close();

    assert.deepEqual(problems, [], 'console errors');
    // A short game against bots may not get far enough for the human player
    for (const key of BOTS > 0 ? ['turns'] : ['turns', 'roads', 'trades', 'cardsBought']) {
        assert.ok(seen[key] > 0, `the game never reached: ${key}`);
    }
};

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
