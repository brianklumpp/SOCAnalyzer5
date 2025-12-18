import React from 'react';

type TimelineEvent = {
  label: string;
  date: string | null;
};

type CompactTimelineProps = {
  events: TimelineEvent[];
  width?: number; // overall SVG width
  boxWidth?: number; // width of the event pill
  pillFill?: string; // background color of event pills
  textFill?: string; // text color
};

// A compact, centered vertical timeline rendered as SVG.
// - Center line is exactly in the middle
// - Each event is a rounded pill centered on the line, keeping content near the middle
// - Works well in constrained columns and aligns visually with content below
export default function CompactTimeline({ events, width = 420, boxWidth = 260, pillFill = '#d198ed', textFill = '#333' }: CompactTimelineProps) {
  const topPadding = 14;
  const between = 34; // space between event centers
  const boxHeight = 22;
  const cx = Math.floor(width / 2);
  const height = topPadding * 2 + (events.length - 1) * between + boxHeight + 6;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Timeline">
      {/* Center vertical line */}
      <line x1={cx} y1={topPadding - 4} x2={cx} y2={height - topPadding + 4} stroke="#b0bec5" strokeWidth={2} />

      {events.map((e, i) => {
        const cy = topPadding + i * between + Math.floor(boxHeight / 2);
        const x = Math.max(8, cx - Math.floor(boxWidth / 2));
        const rx = 8;
        return (
          <g key={`${e.label}-${i}`}>
            {/* Node dot */}
            <circle cx={cx} cy={cy} r={5} fill="#607d8b" />
            {/* Event pill */}
            <rect x={x} y={cy - Math.floor(boxHeight / 2)} width={boxWidth} height={boxHeight} rx={rx} ry={rx} fill={pillFill} stroke="#cfd8dc" />
            {/* Text (label: date) */}
            <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" fontSize="10" fill={textFill}>
              {e.label}: {e.date || '-'}
            </text>
          </g>
        );
      })}
    </svg>
  );
}


