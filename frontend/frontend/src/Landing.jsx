import React from "react";

export default function Landing({ onStart }) {
  return (
    <div className="min-h-screen bg-neutral-950 text-white flex flex-col items-center justify-center px-6">

      <div className="max-w-3xl text-center space-y-6">

        <h1 className="text-5xl md:text-6xl font-bold leading-tight">
          Know what's actually open.
        </h1>

        <h2 className="text-xl md:text-2xl text-neutral-300">
          Not just what's on the map.
        </h2>

        <p className="text-lg text-neutral-400 mt-4">
          Get supermarkets, water and bike shops along your route —
          with the most up-to-date data available.
        </p>

        <p className="text-lg text-neutral-300">
          Plan your stops. Ride more efficiently.
        </p>

        <button
          onClick={onStart}
          className="mt-6 px-8 py-4 bg-white text-black rounded-xl text-lg font-semibold hover:bg-neutral-200 transition"
        >
          Get Started
        </button>

        <p className="text-sm text-neutral-500">
          No signup — just upload your GPX
        </p>
      </div>
    </div>
  );
}