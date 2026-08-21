/**
 * 7社比較結果ページ（/compare）
 */
(function initComparePage(global) {
  const CARRIERS_BY_ID = Object.fromEntries(
    (readSimulatorConfig().carriers || []).map((carrier) => [carrier.id, carrier])
  );

  function readSimulatorConfig() {
    const node = document.getElementById("simulator-config");
    if (!node) return {};
    try {
      return JSON.parse(node.textContent);
    } catch {
      return {};
    }
  }

  function parseLineIndices(params) {
    const indices = new Set();
    params.forEach((_value, key) => {
      const match = key.match(/^lines\[(\d+)\]/);
      if (match) indices.add(Number(match[1]));
    });
    return [...indices].sort((left, right) => left - right);
  }

  function lineParam(params, index, name) {
    return params.get(`lines[${index}][${name}]`) || "";
  }

  function hasTruthyParam(params, name) {
    const value = params.get(name);
    return value !== null && value !== "" && value !== "0";
  }

  function formatDataUsage(params, index) {
    const usage = lineParam(params, index, "data_usage");
    if (usage === "unlimited") return "無制限";
    if (!usage) return "—";
    return `${usage}GB`;
  }

  function formatYen(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "";
    return `${amount.toLocaleString("ja-JP")}円`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function collectLineDetailNotes(params, index) {
    const notes = [];
    const paypayAmount = lineParam(params, index, "qr_paypay");
    if (paypayAmount) notes.push(`PayPay ${Number(paypayAmount).toLocaleString("ja-JP")}円/月`);
    const dbaraiAmount = lineParam(params, index, "qr_dbarai");
    if (dbaraiAmount) notes.push(`d払い ${Number(dbaraiAmount).toLocaleString("ja-JP")}円/月`);
    const aupayAmount = lineParam(params, index, "qr_aupay");
    if (aupayAmount) notes.push(`au PAY ${Number(aupayAmount).toLocaleString("ja-JP")}円/月`);
    const paypayTier = lineParam(params, index, "paypay_card_tier");
    if (paypayTier) notes.push(`PayPayカード ${paypayTier === "gold" ? "ゴールド" : "ノーマル"}`);
    if (lineParam(params, index, "paypay_gold_linked")) notes.push("PayPay GOLD連携あり");
    if (lineParam(params, index, "docomo_bill_dcard")) notes.push("通信料をdカード支払い");
    const auBillMode = lineParam(params, index, "au_bill_payment_mode");
    if (auBillMode && auBillMode !== "other") {
      notes.push(
        auBillMode === "au_pay_card"
          ? "au PAYカードで通信料支払い"
          : "auじぶん銀行口座振替"
      );
    }
    if (lineParam(params, index, "au_jibun_bank_balance")) notes.push("auじぶん銀行残高：入力あり");
    if (lineParam(params, index, "aupay_gold")) notes.push("au PAYゴールド");
    return notes;
  }

  function collectAccountDetailNotes(params) {
    const notes = [];
    if (hasTruthyParam(params, "home_set_softbank")) notes.push("SoftBank光セット");
    if (hasTruthyParam(params, "home_set_au")) notes.push("auひかりセット");
    if (hasTruthyParam(params, "home_set_docomo")) notes.push("ドコモ光セット");
    if (hasTruthyParam(params, "home_set_docomo_denki")) notes.push("ドコモでんきセット");
    if (hasTruthyParam(params, "tenure_years")) notes.push(`利用年数 ${params.get("tenure_years")}年`);
    return notes;
  }

  function renderConditionSummary(queryString) {
    const container = document.getElementById("compare-conditions-summary");
    if (!container) return;

    let params;
    try {
      params = new URLSearchParams(queryString);
    } catch {
      container.innerHTML =
        '<p class="text-[14px] text-red-700">比較条件を読み込めませんでした</p>';
      return;
    }

    const indices = parseLineIndices(params);
    const lineRows = indices
      .map((index) => {
        const carrierId = lineParam(params, index, "carrier") || "softbank";
        const carrierName = CARRIERS_BY_ID[carrierId]?.name || carrierId;
        const age = lineParam(params, index, "age");
        const ageLabel = age ? `${age}歳` : "年齢未入力";
        const dataLabel = formatDataUsage(params, index);
        const label = index === 0 ? "主回線" : `${index + 1}回線目`;
        return `<li class="text-[14px] leading-relaxed text-slate-700"><span class="font-semibold text-slate-900">${escapeHtml(label)}（${escapeHtml(carrierName)}）</span>：${escapeHtml(ageLabel)} / ${escapeHtml(dataLabel)}</li>`;
      })
      .join("");

    const currentPrice = params.get("current_price");
    const currentPriceRow = currentPrice
      ? `<p class="mt-2 text-[14px] text-slate-700"><span class="font-semibold text-slate-900">現在の月額</span>：${escapeHtml(formatYen(currentPrice))} / 月</p>`
      : "";

    const detailNotes = [
      ...indices.flatMap((index) => collectLineDetailNotes(params, index)),
      ...collectAccountDetailNotes(params),
    ];
    const uniqueNotes = [...new Set(detailNotes)];
    const detailHtml = uniqueNotes.length
      ? `<div class="mt-3 border-t border-slate-200 pt-3">
          <p class="text-[12px] font-semibold text-slate-600">主な詳細条件</p>
          <ul class="mt-1 space-y-1">${uniqueNotes.map((note) => `<li class="text-[13px] text-slate-700">${escapeHtml(note)}</li>`).join("")}</ul>
        </div>`
      : "";

    container.innerHTML = `<div class="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <p class="text-[13px] font-semibold text-slate-800">今回の比較条件</p>
      <p class="mt-1 text-[13px] text-slate-600">${indices.length}回線</p>
      <ul class="mt-2 space-y-1">${lineRows}</ul>
      ${currentPriceRow}
      ${detailHtml}
    </div>`;
  }

  function showEmptyState(message) {
    document.getElementById("compare-empty-state")?.classList.remove("hidden");
    document.getElementById("compare-content")?.classList.add("hidden");
    const text = document.getElementById("compare-empty-message");
    if (text) text.textContent = message;
  }

  function showContent() {
    document.getElementById("compare-empty-state")?.classList.add("hidden");
    document.getElementById("compare-content")?.classList.remove("hidden");
  }

  async function loadCompareResult(queryString) {
    showContent();
    renderConditionSummary(queryString);
    global.CompareUI?.showCompareLoading?.();

    try {
      const response = await fetch(`/api/compare?${queryString}`);
      if (response.status === 400) {
        global.CompareUI?.showCompareError?.();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      global.CompareUI?.renderCompareResult?.(payload, CARRIERS_BY_ID);
    } catch {
      global.CompareUI?.showCompareError?.();
    }
  }

  function bindActions() {
    document.getElementById("compare-edit-button")?.addEventListener("click", () => {
      window.location.href = global.SimulatorState?.buildSimulatorUrlFromStored?.() || "/";
    });
    document.getElementById("compare-empty-back-button")?.addEventListener("click", () => {
      window.location.href = "/";
    });
  }

  function bootstrapComparePage() {
    bindActions();
    const queryString = global.SimulatorState?.loadCompareInput?.();
    if (!queryString) {
      showEmptyState("比較条件がありません。入力ページで条件を設定してください。");
      return;
    }
    loadCompareResult(queryString);
  }

  if (document.querySelector('[data-page="compare"]')) {
    bootstrapComparePage();
  }
})(window);
