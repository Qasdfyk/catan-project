/**
 * What the platform keeps and what sharing a game for research means. The
 * rules it describes live in backend/app/services/human_records.py and
 * docs/human-records.md; change all three together.
 */
export const Terms = () => (
    <main className="center-page">
        <article className="card terms">
            <h1>Terms and your games</h1>

            <h2>What every game keeps</h2>
            <p>
                When a game ends, the server saves its record: the board, every move, and the names typed in
                the lobby. That is what <em>Download</em> and <em>Review this game</em> use. Chat messages are
                not part of it.
            </p>

            <h2>Sharing a game for research</h2>
            <p>
                In the lobby each person can tick <em>Share this game for research</em>. It is off unless you
                tick it, and you can untick it until the game starts. A game is shared only if every person at
                the table agreed. Bots need no answer, and a bot that finishes the game of somebody who left
                does not answer for them.
            </p>
            <p>A shared game is copied, apart from the other records, without anything that tells who played:</p>
            <ul>
                <li>names become “Player 1”, “Bot 2” and so on, by seat;</li>
                <li>the room ID and link are replaced by a random ID;</li>
                <li>only the date is kept, not the time of day.</li>
            </ul>
            <p>
                The copy is anonymous for anyone who reads the dataset. The server's own record of the same
                game, with names, stays as described above, so whoever runs the server could still match the two.
            </p>

            <h2>What the copies are for</h2>
            <p>
                Only to measure how well the open source{' '}
                <a href="https://github.com/Qasdfyk/catan-analysis-engine">catan-analysis-engine</a>{' '}
                reviews human play. They are not used to train any model, not sold and not given to anyone.
                Only numbers computed from many games are published, never the games themselves.
            </p>

            <h2>Changing your mind</h2>
            <p>
                Before the game starts, untick the box. After that the copy holds no name, so nobody can tell
                which one was yours, and it cannot be picked out and removed. If you are unsure, leave the box
                empty: the game plays the same.
            </p>

            <p className="muted">
                Questions: open an issue at{' '}
                <a href="https://github.com/Qasdfyk/catan-project/issues">github.com/Qasdfyk/catan-project</a>.
            </p>
            <a className="button" href="/">Back to the game</a>
        </article>
    </main>
);
