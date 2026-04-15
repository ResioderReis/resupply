import React from "react";

export default function Landing() {
  return (
    <div className="min-h-screen bg-neutral-950 text-white flex flex-col items-center justify-center px-6">

      {/* HERO */}
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

        <button className="mt-6 px-8 py-4 bg-white text-black rounded-xl text-lg font-semibold hover:bg-neutral-200 transition">
          Get Started
        </button>

        <p className="text-sm text-neutral-500">
          No signup — just upload your GPX
        </p>
      </div>

      {/* SPACING */}
      <div className="h-32" />

      {/* PROBLEM */}
      <div className="max-w-2xl text-center space-y-4">
        <p className="text-neutral-400">
          You've been there:
        </p>

        <div className="text-lg space-y-2 text-neutral-300">
          <p>• The place exists</p>
          <p>• But it's closed</p>
          <p>• Or not even there anymore</p>
        </div>

        <p className="text-neutral-500 mt-4">
          Planning is easy. Reality isn't.
        </p>
      </div>

      {/* SPACING */}
      <div className="h-32" />

      {/* SOLUTION */}
      <div className="max-w-2xl text-center space-y-4">
        <h3 className="text-2xl font-semibold">
          Resupply gives you a better guess.
        </h3>

        <div className="text-neutral-300 space-y-2">
          <p>✔ Opening hours from real data sources</p>
          <p>✔ Places people actually use</p>
          <p>✔ Filtered along your route</p>
        </div>

        <p className="text-neutral-500 mt-4">
          Not perfect. But a lot better than guessing.
        </p>
      </div>

      {/* SPACING */}
      <div className="h-32" />

      {/* HOW IT WORKS */}
      <div className="max-w-2xl text-center space-y-4">
        <h3 className="text-2xl font-semibold">
          How it works
        </h3>

        <div className="text-neutral-300 space-y-2">
          <p>1. Upload your GPX</p>
          <p>2. Choose your radius</p>
          <p>3. See what’s actually usable</p>
        </div>
      </div>

      {/* SPACING */}
      <div className="h-32" />

      {/* CTA */}
      <div className="text-center space-y-6">
        <h3 className="text-3xl font-semibold">
          Ride with fewer surprises.
        </h3>

        <button className="px-8 py-4 bg-white text-black rounded-xl text-lg font-semibold hover:bg-neutral-200 transition">
          Get Started
        </button>
      </div>

      {/* FOOTER */}
      <div className="h-20" />
    </div>
  );
}