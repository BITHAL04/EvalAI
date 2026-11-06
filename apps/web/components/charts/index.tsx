"use client";

import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const AXIS = { fontSize: 12, fill: "#5b6478" };
const C = { primary: "#3730a3", muted: "#9aa3b5", mark: "#c0261b", success: "#047857" };

export function ScoreDistribution({ data }: { data: { range: string; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ left: -20, right: 8 }}>
        <CartesianGrid vertical={false} stroke="#e3e6ee" />
        <XAxis dataKey="range" tick={AXIS} tickLine={false} axisLine={false} label={{ value: "Score %", position: "insideBottom", offset: -2, fontSize: 11, fill: "#5b6478" }} height={40} />
        <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip cursor={{ fill: "#f5f6f9" }} formatter={(v) => [v, "Students"]} />
        <Bar dataKey="count" fill={C.primary} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function QuestionAverages({ data }: { data: { label: string; average: number | null }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ left: -20, right: 8 }}>
        <CartesianGrid vertical={false} stroke="#e3e6ee" />
        <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis domain={[0, 100]} tick={AXIS} tickLine={false} axisLine={false} unit="%" />
        <Tooltip cursor={{ fill: "#f5f6f9" }} formatter={(v) => [`${v}%`, "Average score"]} />
        <Bar dataKey="average" fill={C.primary} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TopicBars({ data }: { data: { name: string; score: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 24 }}>
        <CartesianGrid horizontal={false} stroke="#e3e6ee" />
        <XAxis type="number" domain={[0, 100]} tick={AXIS} unit="%" tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" tick={AXIS} width={150} tickLine={false} axisLine={false} />
        <Tooltip cursor={{ fill: "#f5f6f9" }} formatter={(v) => [`${v}%`, "Score"]} />
        <Bar dataKey="score" fill={C.primary} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TopicRadar({ data }: { data: { name: string; score: number }[] }) {
  if (data.length < 3) return <TopicBars data={data} />;
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#e3e6ee" />
        <PolarAngleAxis dataKey="name" tick={{ fontSize: 11, fill: "#5b6478" }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Radar dataKey="score" stroke={C.primary} fill={C.primary} fillOpacity={0.2} />
        <Tooltip formatter={(v) => [`${v}%`, "Mastery"]} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

export function Trend({ data }: { data: { examination: string; percentage: number; class_average: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ left: -20, right: 12 }}>
        <CartesianGrid vertical={false} stroke="#e3e6ee" />
        <XAxis dataKey="examination" tick={false} axisLine={false} />
        <YAxis domain={[0, 100]} tick={AXIS} unit="%" tickLine={false} axisLine={false} />
        <Tooltip formatter={(v, n) => [`${v}%`, n === "percentage" ? "You" : "Class average"]} />
        <Legend formatter={(v) => (v === "percentage" ? "You" : "Class average")} wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="percentage" stroke={C.primary} strokeWidth={2.5} dot={{ r: 3 }} />
        <Line type="monotone" dataKey="class_average" stroke={C.muted} strokeDasharray="4 4" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ClassComparison({ data }: { data: { examination: string; average: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ left: -20, right: 8 }}>
        <CartesianGrid vertical={false} stroke="#e3e6ee" />
        <XAxis dataKey="examination" tick={false} axisLine={false} />
        <YAxis domain={[0, 100]} tick={AXIS} unit="%" tickLine={false} axisLine={false} />
        <Tooltip cursor={{ fill: "#f5f6f9" }} formatter={(v) => [`${v}%`, "Class average"]} />
        <Bar dataKey="average" fill={C.success} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
