/**
 * 入力ページ ↔ 比較ページ間の一時state（sessionStorage・タブ単位）
 */
(function initSimulatorState(global) {
  const STORAGE_KEY = "mobile_simulator_compare_input";
  const VERSION = 1;

  function saveCompareInput(queryString) {
    if (typeof queryString !== "string" || !queryString.trim()) return false;
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: VERSION, params: queryString })
    );
    return true;
  }

  function loadCompareInput() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (parsed?.version !== VERSION || typeof parsed?.params !== "string") return null;
      return parsed.params;
    } catch {
      return null;
    }
  }

  function buildSimulatorUrlFromStored() {
    const params = loadCompareInput();
    return params ? `/?${params}` : "/";
  }

  global.SimulatorState = {
    STORAGE_KEY,
    VERSION,
    saveCompareInput,
    loadCompareInput,
    buildSimulatorUrlFromStored,
  };
})(window);
