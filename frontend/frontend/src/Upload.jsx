import React, { useState } from "react";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [radius, setRadius] = useState(2);

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log("File:", file);
    console.log("Radius:", radius);
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-white flex flex-col items-center justify-center px-6">

      <div className="max-w-xl w-full space-y-8">

        <h1 className="text-3xl font-bold text-center">
          Upload your route
        </h1>

        {/* Upload */}
        <div className="border border-neutral-700 rounded-xl p-6 text-center">
          <input
            type="file"
            accept=".gpx"
            onChange={(e) => setFile(e.target.files[0])}
            className="text-sm"
          />
          <p className="text-neutral-400 mt-2">
            GPX only
          </p>
        </div>

        {/* Radius */}
        <div>
          <label className="block mb-2 text-neutral-300">
            Radius: {radius} km
          </label>

          <input
            type="range"
            min="1"
            max="10"
            value={radius}
            onChange={(e) => setRadius(e.target.value)}
            className="w-full"
          />
        </div>

        {/* Button */}
        <button
          onClick={handleSubmit}
          className="w-full py-4 bg-white text-black rounded-xl font-semibold hover:bg-neutral-200 transition"
        >
          Analyze Route
        </button>

      </div>
    </div>
  );
}