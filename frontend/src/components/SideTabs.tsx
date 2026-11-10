import { useState, type ReactNode } from 'react';

export interface SideTab {
    id: string;
    label: string;
    /** A small count next to the label, such as unread messages; hidden when 0. */
    badge?: number;
    content: ReactNode;
}

interface SideTabsProps {
    tabs: SideTab[];
    /** Told when a tab is opened, so a caller can mark what was in it as seen. */
    onOpen?: (id: string) => void;
}

/**
 * The lower part of the side panel: the log, the chat and the dice statistics share
 * one box with tabs instead of stacking up, so the panels that matter on a turn
 * (players, building, trading) stay in view.
 */
export const SideTabs = ({ tabs, onOpen }: SideTabsProps) => {
    const [active, setActive] = useState(tabs[0].id);
    const open = (id: string) => {
        setActive(id);
        onOpen?.(id);
    };

    return (
        <section className="panel side-tabs" aria-label="Log, chat and dice">
            <div className="tab-list" role="tablist">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        id={`tab-${tab.id}`}
                        role="tab"
                        aria-selected={tab.id === active}
                        aria-controls={`tabpanel-${tab.id}`}
                        className="tab"
                        onClick={() => open(tab.id)}
                    >
                        {tab.label}
                        {(tab.badge ?? 0) > 0 && <span className="tab-badge">{tab.badge}</span>}
                    </button>
                ))}
            </div>
            {tabs.map((tab) => (
                <div
                    key={tab.id}
                    id={`tabpanel-${tab.id}`}
                    role="tabpanel"
                    aria-labelledby={`tab-${tab.id}`}
                    className="tab-panel"
                    hidden={tab.id !== active}
                >
                    {tab.content}
                </div>
            ))}
        </section>
    );
};
