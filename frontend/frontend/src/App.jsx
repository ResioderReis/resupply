import { useState } from "react";
import Landing from "./Landing";
import Upload from "./Upload";

function App() {
  const [screen, setScreen] = useState("landing");

  return (
    <>
      {screen === "landing" && (
        <Landing onStart={() => setScreen("upload")} />
      )}

      {screen === "upload" && <Upload />}
    </>
  );
}

export default App;