import { useEffect, useRef } from "react";
import type { BoardPost } from "../events/reduce";
import { attackerColor } from "../scene/palette";

interface Props {
  posts: BoardPost[];
  attackerIndex: Record<string, number>;
  labels: Record<string, string>;
  selectedPostId: string | null;
  onSelect(postId: string): void;
  onLayout(anchors: { board: { x: number; y: number } | null; posts: Record<string, { x: number; y: number }> }): void;
}

export function MessageBoard({ posts, attackerIndex, labels, selectedPostId, onSelect, onLayout }: Props) {
  const rootRef = useRef<HTMLElement>(null);
  const postRefs = useRef(new Map<string, HTMLButtonElement>());

  useEffect(() => {
    const root = rootRef.current;
    const stage = root?.closest(".stage");
    if (!root || !stage) return;
    const stageBox = stage.getBoundingClientRect();
    const rootBox = root.getBoundingClientRect();
    const postAnchors: Record<string, { x: number; y: number }> = {};
    for (const [id, node] of postRefs.current) {
      const box = node.getBoundingClientRect();
      postAnchors[id] = {
        x: box.left - stageBox.left,
        y: box.top - stageBox.top + box.height / 2,
      };
    }
    onLayout({
      board: { x: rootBox.left - stageBox.left, y: rootBox.top - stageBox.top + 36 },
      posts: postAnchors,
    });
  }, [posts, onLayout]);

  return (
    <aside className="board" ref={rootRef} aria-label="Team messageboard">
      <header>
        <h2>Team messageboard</h2>
        <p className="stamp">Hidden from defender</p>
      </header>
      <ol>
        {posts.length === 0 ? <li className="empty">No posts in the events shown.</li> : null}
        {posts.map((post) => {
          const index = post.authorId ? attackerIndex[post.authorId] : undefined;
          const color = index === undefined ? "#6b645b" : attackerColor(index);
          const label = post.authorId ? (labels[post.authorId] ?? post.authorId) : "unknown";
          return (
            <li key={post.id}>
              <button
                type="button"
                ref={(node) => {
                  if (node) postRefs.current.set(post.id, node);
                  else postRefs.current.delete(post.id);
                }}
                className={selectedPostId === post.id ? "post selected" : "post"}
                style={{ borderLeftColor: color }}
                onClick={() => onSelect(post.id)}
              >
                <span className="post-meta">
                  post {post.postId} · {label} · round {post.round}
                </span>
                <span className="post-text">
                  {post.charCount} characters. Post text is behind a payload ref and is not on this projection.
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
