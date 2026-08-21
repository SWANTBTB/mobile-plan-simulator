/**
 * 全キャリア横断比較結果UI（/api/compare 専用）
 * axis_quotes を正規情報源とし、料金の再計算は行わない。
 */
(function initCompareUi(global) {
  const DEFAULT_THEME = { border: "border-slate-300", bg: "bg-slate-50" };

  function formatYen(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "---円";
    return `${amount.toLocaleString("ja-JP")}円`;
  }

  function formatYenEquivalent(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "---円相当";
    return `${amount.toLocaleString("ja-JP")}円相当`;
  }

  function formatPoints(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "---pt";
    return `${amount.toLocaleString("ja-JP")}pt`;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function carrierTheme(carrierId, carriersById) {
    return carriersById?.[carrierId]?.theme || DEFAULT_THEME;
  }

  function aggregateRewards(lines) {
    const items = [];
    (lines || []).forEach((line) => {
      (line.rewards || []).forEach((reward) => {
        items.push(reward);
      });
    });
    return items;
  }

  function planLabel(lines) {
    const names = [];
    (lines || []).forEach((line) => {
      if (line.plan_name && !names.includes(line.plan_name)) {
        names.push(line.plan_name);
      }
    });
    return names.join(" / ") || "—";
  }

  function bundledServicesLabel(lines) {
    const names = [];
    (lines || []).forEach((line) => {
      (line.bundled_services || []).forEach((service) => {
        const name = service.name || "付帯サービス";
        if (!names.includes(name)) names.push(name);
      });
    });
    return names;
  }

  function normalizePlanIds(source) {
    if (!source) return [];
    if (Array.isArray(source.plan_ids) && source.plan_ids.length) {
      return source.plan_ids.map(String);
    }
    if (source.plan_id) return [String(source.plan_id)];
    const lines = source.lines || [];
    const fromLines = lines.map((line) => line.plan_id).filter(Boolean);
    if (fromLines.length) return fromLines.map(String);
    return [];
  }

  function planIdsEqual(left, right) {
    const a = normalizePlanIds(left);
    const b = normalizePlanIds(right);
    if (a.length !== b.length) return false;
    return a.every((value, index) => value === b[index]);
  }

  function getAxisQuotes(entry) {
    if (entry?.axis_quotes?.billing && entry.axis_quotes.effective && entry.axis_quotes.value_adjusted) {
      return entry.axis_quotes;
    }
    const lines = entry.lines || [];
    const legacy = {
      plan_id: lines[0]?.plan_id,
      plan_name: planLabel(lines),
      plan_ids: lines.map((line) => line.plan_id).filter(Boolean),
      lines,
    };
    return {
      billing: {
        ...legacy,
        billing_total: entry.billing_total,
        reward_total: entry.reward_total,
        effective_total: entry.effective_total,
        value_adjusted_total: entry.value_adjusted_total,
        bundled_value: entry.bundled_value,
      },
      effective: {
        ...legacy,
        billing_total: entry.billing_total,
        reward_total: entry.reward_total,
        effective_total: entry.effective_total,
        value_adjusted_total: entry.value_adjusted_total,
        bundled_value: entry.bundled_value,
      },
      value_adjusted: {
        ...legacy,
        billing_total: entry.billing_total,
        reward_total: entry.reward_total,
        effective_total: entry.effective_total,
        value_adjusted_total: entry.value_adjusted_total,
        bundled_value: entry.bundled_value,
      },
    };
  }

  function lineCountLabel(count) {
    return count > 1 ? "世帯" : "";
  }

  function renderPlanName(quote) {
    const lines = quote.lines || [];
    const uniqueNames = [...new Set(lines.map((line) => line.plan_name).filter(Boolean))];
    if (uniqueNames.length <= 1) {
      return escapeHtml(uniqueNames[0] || quote.plan_name || "—");
    }
    const items = lines
      .map((line) => {
        const label = line.line_index === 0 ? "主回線" : `${(line.line_index || 0) + 1}回線目`;
        return `<li class="flex justify-between gap-2"><span class="text-slate-500">${escapeHtml(label)}</span><span class="font-medium text-slate-800">${escapeHtml(line.plan_name || "—")}</span></li>`;
      })
      .join("");
    return `<details class="compare-plan-lines mt-1">
      <summary class="cursor-pointer text-[12px] font-medium text-slate-700">回線ごとのプランを見る（${lines.length}回線）</summary>
      <ul class="mt-2 space-y-1">${items}</ul>
    </details>`;
  }

  function valueDiffersFromEffective(valueQuote, effectiveQuote) {
    const bundled = Number(valueQuote?.bundled_value) || 0;
    if (bundled <= 0) return false;
    return Number(valueQuote?.value_adjusted_total) !== Number(effectiveQuote?.effective_total);
  }

  function buildPlanBlockGroups(entry) {
    const quotes = getAxisQuotes(entry);
    const billing = quotes.billing;
    const effective = quotes.effective;
    const valueQuote = quotes.value_adjusted;
    const allSamePlan =
      planIdsEqual(billing, effective) &&
      planIdsEqual(effective, valueQuote) &&
      !valueDiffersFromEffective(valueQuote, effective);

    if (allSamePlan) {
      return [
        {
          kind: "unified",
          planIds: normalizePlanIds(billing),
          billing,
          effective,
          valueQuote,
          axisLabels: [],
        },
      ];
    }

    const blocks = [];
    const billingSeparate = !planIdsEqual(billing, effective);
    if (billingSeparate) {
      blocks.push({
        kind: "billing",
        planIds: normalizePlanIds(billing),
        quote: billing,
        axisLabels: ["料金だけなら"],
      });
    }

    const valueSeparate =
      !planIdsEqual(valueQuote, effective) || valueDiffersFromEffective(valueQuote, effective);
    if (!valueSeparate && !billingSeparate) {
      blocks.push({
        kind: "effective",
        planIds: normalizePlanIds(effective),
        quote: effective,
        axisLabels: ["還元まで含めると"],
      });
    } else if (!valueSeparate) {
      blocks.push({
        kind: "effective",
        planIds: normalizePlanIds(effective),
        quote: effective,
        axisLabels: ["還元まで含めると"],
      });
    } else if (planIdsEqual(effective, valueQuote)) {
      blocks.push({
        kind: "effective-value",
        planIds: normalizePlanIds(effective),
        quote: effective,
        valueQuote,
        axisLabels: ["還元まで含めると", "付帯サービスまで含めると"],
      });
    } else {
      blocks.push({
        kind: "effective",
        planIds: normalizePlanIds(effective),
        quote: effective,
        axisLabels: ["還元まで含めると"],
      });
      blocks.push({
        kind: "value",
        planIds: normalizePlanIds(valueQuote),
        quote: valueQuote,
        axisLabels: ["付帯サービスまで含めると"],
      });
    }

    return blocks;
  }

  function isCheapestAxis(entry, cheapestItem, quote) {
    if (!cheapestItem || cheapestItem.carrier_id !== entry.carrier_id) return false;
    return planIdsEqual(cheapestItem, quote);
  }

  function blockBadgeList(entry, block, cheapest) {
    const badges = [];
    const quote = block.quote || block.effective;
    const valueQuote = block.valueQuote || block.quote || block.effective;

    if (block.kind === "unified") {
      if (isCheapestAxis(entry, cheapest?.billing, block.billing)) badges.push("請求額 最安");
      if (isCheapestAxis(entry, cheapest?.effective, block.effective)) badges.push("実質負担 最安");
      if (isCheapestAxis(entry, cheapest?.valueAdjusted, block.valueQuote)) {
        badges.push("付帯サービス込み 最安");
      }
      return badges;
    }

    if (block.kind === "billing" && isCheapestAxis(entry, cheapest?.billing, quote)) {
      badges.push("請求額 最安");
    }
    if ((block.kind === "effective" || block.kind === "effective-value") && isCheapestAxis(entry, cheapest?.effective, quote)) {
      badges.push("実質負担 最安");
    }
    if ((block.kind === "value" || block.kind === "effective-value") && isCheapestAxis(entry, cheapest?.valueAdjusted, valueQuote)) {
      badges.push("付帯サービス込み 最安");
    }
    return badges;
  }

  function renderRewardBreakdown(rewards) {
    if (!rewards.length) {
      return `<p class="compare-reward-empty text-[12px] text-slate-500">還元なし</p>`;
    }

    return `<ul class="compare-reward-list mt-1 space-y-1">
      ${rewards
        .map((reward) => {
          const amount = Number(reward.amount) || 0;
          const label = escapeHtml(reward.name || reward.id || "還元");
          const value =
            reward.type === "CASH"
              ? `${amount.toLocaleString("ja-JP")}円還元`
              : `${amount.toLocaleString("ja-JP")}pt`;
          return `<li class="flex items-baseline justify-between gap-2 text-[12px] text-slate-600">
            <span>${label}</span>
            <span class="tabular-nums font-medium text-slate-700" data-compare-reward-type="${escapeHtml(reward.type || "")}">${value}</span>
          </li>`;
        })
        .join("")}
    </ul>`;
  }

  function filterDuplicateRewardStrengths(strengths, rewards) {
    if (!Array.isArray(strengths) || !strengths.length) return [];
    const rewardIds = new Set((rewards || []).map((reward) => reward.id).filter(Boolean));
    if (!rewardIds.size) return strengths;

    return strengths.filter((strength) => {
      const evidence = strength?.evidence;
      if (!evidence || typeof evidence !== "object") return true;
      const rewardId = evidence.reward_id;
      if (!rewardId || !rewardIds.has(rewardId)) return true;
      return false;
    });
  }

  function badgeList(entry, cheapest) {
    const quotes = getAxisQuotes(entry);
    const badges = [];
    if (isCheapestAxis(entry, cheapest?.billing, quotes.billing)) badges.push("請求額 最安");
    if (isCheapestAxis(entry, cheapest?.effective, quotes.effective)) badges.push("実質負担 最安");
    if (isCheapestAxis(entry, cheapest?.valueAdjusted, quotes.value_adjusted)) {
      badges.push("付帯サービス込み 最安");
    }
    return badges;
  }

  function renderBadges(badges) {
    if (!badges.length) return "";
    return `<div class="compare-badges mt-2 flex flex-wrap gap-1.5">
      ${badges
        .map(
          (label) =>
            `<span class="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-semibold text-blue-800">${escapeHtml(label)}</span>`
        )
        .join("")}
    </div>`;
  }

  function renderAxisLabels(labels) {
    if (!labels.length) return "";
    return `<div class="compare-axis-labels flex flex-wrap gap-1.5">
      ${labels
        .map(
          (label) =>
            `<span class="rounded bg-slate-200/80 px-2 py-0.5 text-[11px] font-semibold text-slate-700">${escapeHtml(label)}</span>`
        )
        .join("")}
    </div>`;
  }

  function renderStrengths(strengths) {
    if (!strengths?.length) return "";
    return `<div class="compare-strengths mt-4 border-t border-slate-100 pt-3">
      <p class="text-[12px] font-semibold text-slate-700">あなたの条件での特徴</p>
      <p class="mt-0.5 text-[11px] text-slate-500">還元込みで選ばれたプランの特徴</p>
      <ul class="mt-2 space-y-1.5">
        ${strengths
          .slice(0, 3)
          .map(
            (item) =>
              `<li class="flex gap-2 text-[12px] leading-relaxed text-slate-700">
                <span class="text-emerald-600" aria-hidden="true">✓</span>
                <span>${escapeHtml(item.message)}</span>
              </li>`
          )
          .join("")}
      </ul>
    </div>`;
  }

  function renderCautions(cautions) {
    if (!cautions?.length) return "";
    return `<div class="compare-cautions mt-3 border-t border-slate-100 pt-3">
      <p class="text-[12px] font-semibold text-amber-800">注意点</p>
      <ul class="mt-2 space-y-1.5">
        ${cautions
          .slice(0, 2)
          .map(
            (item) =>
              `<li class="text-[12px] leading-relaxed text-amber-900">${escapeHtml(item.message)}</li>`
          )
          .join("")}
      </ul>
    </div>`;
  }

  function renderErrorCard(entry, theme) {
    const message =
      entry.status === "no_eligible_plan"
        ? "この条件で対象プランを算出できませんでした"
        : "このキャリアの料金を計算できませんでした";
    return `<article class="compare-card compare-card--error ${theme.bg} border ${theme.border} rounded-lg border-l-[3px] p-4">
      <h3 class="text-[15px] font-bold text-slate-900">${escapeHtml(entry.carrier_name || entry.carrier_id)}</h3>
      <p class="mt-2 text-[13px] text-red-700">${message}</p>
    </article>`;
  }

  function renderUnifiedBlock(block, householdLabel) {
    const effective = block.effective;
    const rewards = aggregateRewards(effective.lines);
    const rewardTotal = Number(effective.reward_total) || 0;
    const bundledValue = Number(block.valueQuote?.bundled_value) || 0;
    const showValueAdjusted = valueDiffersFromEffective(block.valueQuote, effective);
    const bundledNames = bundledServicesLabel(block.valueQuote?.lines || effective.lines);

    return `<div class="compare-plan-block compare-plan-block--unified mt-4 rounded-lg border border-slate-200/80 bg-white/60 p-3">
      <p class="compare-plan-block__name text-[14px] font-bold text-slate-900">${renderPlanName(effective)}</p>
      <p class="compare-card__label mt-3 text-[12px] font-semibold text-slate-600">還元込み実質負担</p>
      <p class="compare-card__effective-amount mt-0.5 text-[24px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="effective" data-compare-field="effective_total">
        ${formatYenEquivalent(effective.effective_total)}<span class="text-[14px] font-semibold"> / 月</span>
      </p>
      <div class="compare-card__billing mt-3 border-t border-slate-200/80 pt-3">
        <p class="compare-card__label text-[12px] font-semibold text-slate-600">${householdLabel}実際の請求額</p>
        <p class="compare-card__billing-amount mt-1 text-[18px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="billing" data-compare-field="billing_total">
          ${formatYen(block.billing.billing_total)}<span class="text-[13px] font-semibold text-slate-600"> / 月</span>
        </p>
      </div>
      <div class="compare-card__rewards mt-3 border-t border-slate-200/80 pt-3">
        <p class="compare-card__label text-[12px] font-semibold text-slate-600">還元</p>
        <p class="compare-card__reward-total-amount mt-1 text-[14px] font-semibold tabular-nums text-slate-900" data-compare-axis="effective" data-compare-field="reward_total">${
          rewardTotal > 0 ? formatYenEquivalent(rewardTotal) : "還元なし"
        }</p>
        ${renderRewardBreakdown(rewards)}
      </div>
      ${
        showValueAdjusted
          ? `<dl class="compare-card__amounts mt-3 border-t border-slate-200/80 pt-3 text-[13px]">
          <div class="flex items-baseline justify-between gap-2">
            <dt class="font-medium text-slate-600">付帯サービス込みの比較額</dt>
            <dd class="font-semibold tabular-nums text-slate-900" data-compare-axis="value_adjusted" data-compare-field="value_adjusted_total">${formatYenEquivalent(block.valueQuote.value_adjusted_total)}</dd>
          </div>
        </dl>`
          : ""
      }
      ${
        bundledValue > 0
          ? `<div class="compare-card__bundled mt-2 rounded-md bg-white/70 px-2.5 py-2 text-[12px] text-slate-600">
          <p class="font-medium text-slate-700">付帯サービス</p>
          <p>${escapeHtml(bundledNames.join("・") || "付帯サービス")}（${formatYenEquivalent(bundledValue)}込み）</p>
        </div>`
          : ""
      }
    </div>`;
  }

  function renderBillingBlock(block, badges, householdLabel) {
    const quote = block.quote;
    return `<div class="compare-plan-block compare-plan-block--billing mt-4 rounded-lg border border-slate-200/80 bg-white/60 p-3" data-compare-axis="billing">
      ${renderAxisLabels(block.axisLabels)}
      ${renderBadges(badges)}
      <p class="compare-plan-block__name mt-2 text-[14px] font-bold text-slate-900">${renderPlanName(quote)}</p>
      <p class="compare-card__label mt-3 text-[12px] font-semibold text-slate-600">${householdLabel}実際の請求額</p>
      <p class="compare-card__billing-amount mt-1 text-[24px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="billing" data-compare-field="billing_total">
        ${formatYen(quote.billing_total)}<span class="text-[14px] font-semibold text-slate-600"> / 月</span>
      </p>
    </div>`;
  }

  function renderEffectiveBlock(block, badges, householdLabel) {
    const quote = block.quote;
    const rewards = aggregateRewards(quote.lines);
    const rewardTotal = Number(quote.reward_total) || 0;
    return `<div class="compare-plan-block compare-plan-block--effective mt-4 rounded-lg border border-slate-200/80 bg-white/60 p-3" data-compare-axis="effective">
      ${renderAxisLabels(block.axisLabels)}
      ${renderBadges(badges)}
      <p class="compare-plan-block__name mt-2 text-[14px] font-bold text-slate-900">${renderPlanName(quote)}</p>
      <p class="compare-card__label mt-3 text-[12px] font-semibold text-slate-600">還元込み実質負担</p>
      <p class="compare-card__effective-amount mt-0.5 text-[24px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="effective" data-compare-field="effective_total">
        ${formatYenEquivalent(quote.effective_total)}<span class="text-[14px] font-semibold"> / 月</span>
      </p>
      <div class="compare-card__billing mt-3 border-t border-slate-200/80 pt-3 text-[13px]">
        <div class="flex items-baseline justify-between gap-2">
          <span class="font-medium text-slate-600">${householdLabel}実際の請求額</span>
          <span class="font-semibold tabular-nums text-slate-900" data-compare-axis="effective" data-compare-field="billing_total">${formatYen(quote.billing_total)}</span>
        </div>
        <div class="mt-1 flex items-baseline justify-between gap-2">
          <span class="font-medium text-slate-600">還元</span>
          <span class="font-semibold tabular-nums text-slate-900" data-compare-axis="effective" data-compare-field="reward_total">${
            rewardTotal > 0 ? formatYenEquivalent(rewardTotal) : "還元なし"
          }</span>
        </div>
      </div>
      ${renderRewardBreakdown(rewards)}
    </div>`;
  }

  function renderValueBlock(block, badges, householdLabel) {
    const quote = block.quote;
    const bundledValue = Number(quote.bundled_value) || 0;
    const bundledNames = bundledServicesLabel(quote.lines);
    return `<div class="compare-plan-block compare-plan-block--value mt-4 rounded-lg border border-slate-200/80 bg-white/60 p-3" data-compare-axis="value_adjusted">
      ${renderAxisLabels(block.axisLabels)}
      ${renderBadges(badges)}
      <p class="compare-plan-block__name mt-2 text-[14px] font-bold text-slate-900">${renderPlanName(quote)}</p>
      <p class="compare-card__label mt-3 text-[12px] font-semibold text-slate-600">付帯サービス込みの比較額</p>
      <p class="compare-card__value-amount mt-0.5 text-[24px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="value_adjusted" data-compare-field="value_adjusted_total">
        ${formatYenEquivalent(quote.value_adjusted_total)}<span class="text-[14px] font-semibold"> / 月</span>
      </p>
      <div class="compare-card__billing mt-3 border-t border-slate-200/80 pt-3 text-[13px]">
        <div class="flex items-baseline justify-between gap-2">
          <span class="font-medium text-slate-600">還元込み実質負担</span>
          <span class="font-semibold tabular-nums text-slate-900" data-compare-axis="value_adjusted" data-compare-field="effective_total">${formatYenEquivalent(quote.effective_total)}</span>
        </div>
      </div>
      ${
        bundledValue > 0
          ? `<div class="compare-card__bundled mt-2 rounded-md bg-white/70 px-2.5 py-2 text-[12px] text-slate-600">
          <p class="font-medium text-slate-700">付帯サービス</p>
          <p>${escapeHtml(bundledNames.join("・") || "付帯サービス")}（${formatYenEquivalent(bundledValue)}込み）</p>
        </div>`
          : ""
      }
    </div>`;
  }

  function renderEffectiveValueBlock(block, badges, householdLabel) {
    const quote = block.quote;
    const valueQuote = block.valueQuote;
    const rewards = aggregateRewards(quote.lines);
    const rewardTotal = Number(quote.reward_total) || 0;
    const bundledValue = Number(valueQuote.bundled_value) || 0;
    const bundledNames = bundledServicesLabel(valueQuote.lines);
    return `<div class="compare-plan-block compare-plan-block--effective-value mt-4 rounded-lg border border-slate-200/80 bg-white/60 p-3">
      ${renderAxisLabels(block.axisLabels)}
      ${renderBadges(badges)}
      <p class="compare-plan-block__name mt-2 text-[14px] font-bold text-slate-900">${renderPlanName(quote)}</p>
      <p class="compare-card__label mt-3 text-[12px] font-semibold text-slate-600">還元込み実質負担</p>
      <p class="compare-card__effective-amount mt-0.5 text-[24px] font-bold tabular-nums leading-none text-slate-900" data-compare-axis="effective" data-compare-field="effective_total">
        ${formatYenEquivalent(quote.effective_total)}<span class="text-[14px] font-semibold"> / 月</span>
      </p>
      <div class="compare-card__billing mt-3 border-t border-slate-200/80 pt-3 text-[13px]">
        <div class="flex items-baseline justify-between gap-2">
          <span class="font-medium text-slate-600">${householdLabel}実際の請求額</span>
          <span class="font-semibold tabular-nums text-slate-900" data-compare-axis="effective" data-compare-field="billing_total">${formatYen(quote.billing_total)}</span>
        </div>
        <div class="mt-1 flex items-baseline justify-between gap-2">
          <span class="font-medium text-slate-600">還元</span>
          <span class="font-semibold tabular-nums text-slate-900" data-compare-axis="effective" data-compare-field="reward_total">${
            rewardTotal > 0 ? formatYenEquivalent(rewardTotal) : "還元なし"
          }</span>
        </div>
      </div>
      ${renderRewardBreakdown(rewards)}
      <dl class="compare-card__amounts mt-3 border-t border-slate-200/80 pt-3 text-[13px]">
        <div class="flex items-baseline justify-between gap-2">
          <dt class="font-medium text-slate-600">付帯サービス込みの比較額</dt>
          <dd class="font-semibold tabular-nums text-slate-900" data-compare-axis="value_adjusted" data-compare-field="value_adjusted_total">${formatYenEquivalent(valueQuote.value_adjusted_total)}</dd>
        </div>
      </dl>
      ${
        bundledValue > 0
          ? `<div class="compare-card__bundled mt-2 rounded-md bg-white/70 px-2.5 py-2 text-[12px] text-slate-600">
          <p class="font-medium text-slate-700">付帯サービス</p>
          <p>${escapeHtml(bundledNames.join("・") || "付帯サービス")}（${formatYenEquivalent(bundledValue)}込み）</p>
        </div>`
          : ""
      }
    </div>`;
  }

  function renderPlanBlock(block, entry, cheapest, householdLabel) {
    const badges = blockBadgeList(entry, block, cheapest);
    if (block.kind === "unified") return renderUnifiedBlock(block, householdLabel);
    if (block.kind === "billing") return renderBillingBlock(block, badges, householdLabel);
    if (block.kind === "effective") return renderEffectiveBlock(block, badges, householdLabel);
    if (block.kind === "value") return renderValueBlock(block, badges, householdLabel);
    if (block.kind === "effective-value") return renderEffectiveValueBlock(block, badges, householdLabel);
    return "";
  }

  function renderCarrierCard(entry, cheapest, carriersById) {
    const theme = carrierTheme(entry.carrier_id, carriersById);
    if (entry.status !== "ok") {
      return renderErrorCard(entry, theme);
    }

    const quotes = getAxisQuotes(entry);
    const blocks = buildPlanBlockGroups(entry);
    const effectiveQuote = quotes.effective;
    const rewards = aggregateRewards(effectiveQuote.lines);
    const filteredStrengths = filterDuplicateRewardStrengths(entry.strengths, rewards);
    const lineCount = Math.max(
      ...(blocks.map((block) => (block.quote || block.effective)?.lines?.length || 0)),
      effectiveQuote.lines?.length || 1
    );
    const householdLabel = lineCountLabel(lineCount);
    const headBadges = badgeList(entry, cheapest);

    return `<article class="compare-card ${theme.bg} border ${theme.border} rounded-lg border-l-[3px] p-4" data-carrier-id="${escapeHtml(entry.carrier_id)}">
      <div class="compare-card__head">
        <h3 class="text-[15px] font-bold text-slate-900">${escapeHtml(entry.carrier_name)}</h3>
        ${blocks.length === 1 && blocks[0].kind === "unified" ? renderBadges(headBadges) : ""}
      </div>
      ${blocks.map((block) => renderPlanBlock(block, entry, cheapest, householdLabel)).join("")}
      ${renderStrengths(filteredStrengths)}
      ${renderCautions(entry.cautions)}
    </article>`;
  }

  function currentCostLabel(source) {
    if (source === "estimated_plan_base") {
      return "現在プランの基本料金";
    }
    return "現在の携帯料金";
  }

  function formatSavingMonthlyText(monthlySaving, source) {
    const saving = Number(monthlySaving);
    if (!Number.isFinite(saving)) return "";
    if (saving === 0) {
      return "現在と同額";
    }

    const amount = Math.abs(saving).toLocaleString("ja-JP");
    if (saving > 0) {
      if (source === "estimated_plan_base") {
        return `現在プランの基本料金と比べると<br><span class="font-semibold">月 約${amount}円安い計算です</span>`;
      }
      return `<span class="font-semibold">現在より<br>月 ${amount}円安い</span>`;
    }

    if (source === "estimated_plan_base") {
      return `現在プランの基本料金と比べると<br><span class="font-semibold">月 約${amount}円高い計算です</span>`;
    }
    return `<span class="font-semibold">現在より<br>月 ${amount}円高い</span>`;
  }

  function formatSavingAnnualText(annualSaving, source, monthlySaving) {
    const monthly = Number(monthlySaving);
    if (!Number.isFinite(monthly) || monthly === 0) return "";

    const saving = Number(annualSaving);
    if (!Number.isFinite(saving)) return "";

    const amount = Math.abs(saving).toLocaleString("ja-JP");
    if (source === "estimated_plan_base") {
      return `約${amount}円の差`;
    }
    if (saving > 0) {
      return `約${amount}円安い`;
    }
    return `約${amount}円高い`;
  }

  function savingToneClass(monthlySaving) {
    const saving = Number(monthlySaving);
    if (!Number.isFinite(saving) || saving === 0) return "text-slate-700";
    return saving > 0 ? "text-emerald-700" : "text-amber-800";
  }

  function renderCurrentSavings(data, carriersById) {
    const currentCost = data?.current_cost;
    const savings = data?.savings_summary;
    if (!currentCost || currentCost.source === "unavailable" || !savings) {
      return "";
    }

    const source = savings.source || currentCost.source;
    const cheapestBilling = data.cheapest_billing || {};
    const carrierName =
      cheapestBilling.carrier_name ||
      carriersById?.[savings.carrier_id]?.name ||
      savings.carrier_id;
    const planName = cheapestBilling.plan_name || "";
    const monthlySaving = Number(savings.monthly_saving);
    const monthlyText = formatSavingMonthlyText(monthlySaving, source);
    const annualText = formatSavingAnnualText(savings.annual_saving, source, monthlySaving);
    const toneClass = savingToneClass(monthlySaving);

    return `<div class="compare-savings__block rounded-lg border border-slate-200 bg-slate-50 px-4 py-3" data-compare-savings-source="${escapeHtml(source)}">
      <p class="text-[13px] font-semibold text-slate-800">今の料金と比べると</p>
      <div class="compare-savings__current mt-3">
        <p class="text-[12px] font-medium text-slate-600">${escapeHtml(currentCostLabel(source))}</p>
        <p class="mt-0.5 text-[18px] font-bold tabular-nums text-slate-900" data-compare-savings="current_billing_total">${formatYen(savings.current_billing_total)}<span class="text-[13px] font-semibold"> / 月</span></p>
      </div>
      <p class="compare-savings__arrow my-2 text-center text-[16px] text-slate-400" aria-hidden="true">↓</p>
      <div class="compare-savings__candidate">
        <p class="text-[12px] font-medium text-slate-600">請求額が最も安い</p>
        <p class="mt-0.5 text-[16px] font-bold text-slate-900">${escapeHtml(carrierName)}</p>
        ${planName ? `<p class="text-[13px] font-medium text-slate-700">${escapeHtml(planName)}</p>` : ""}
        <p class="mt-0.5 text-[18px] font-bold tabular-nums text-slate-900" data-compare-savings="new_billing_total">${formatYen(savings.new_billing_total)}<span class="text-[13px] font-semibold"> / 月</span></p>
      </div>
      <p class="compare-savings__monthly mt-3 text-[15px] leading-relaxed ${toneClass}" data-compare-savings="monthly_text">${monthlyText}</p>
      ${
        annualText
          ? `<div class="compare-savings__annual mt-2">
          <p class="text-[12px] font-medium text-slate-600">年間換算</p>
          <p class="mt-0.5 text-[14px] font-semibold tabular-nums ${toneClass}" data-compare-savings="annual_text">${escapeHtml(annualText)}</p>
        </div>`
          : ""
      }
      ${
        annualText
          ? `<p class="compare-savings__note mt-3 text-[11px] leading-relaxed text-slate-500">※年間換算は現在の月額条件が12か月続く場合の参考値です</p>`
          : ""
      }
    </div>`;
  }

  function allCheapestSamePlan(cheapest) {
    const billing = cheapest?.billing;
    const effective = cheapest?.effective;
    const adjusted = cheapest?.valueAdjusted;
    if (!billing || !effective || !adjusted) return false;
    if (billing.carrier_id !== effective.carrier_id || effective.carrier_id !== adjusted.carrier_id) {
      return false;
    }
    return planIdsEqual(billing, effective) && planIdsEqual(effective, adjusted);
  }

  function renderSummaryCombined(carrierName, planName, billing, effective, adjusted) {
    return `<div class="compare-summary__combined rounded-lg border border-blue-100 bg-blue-50 px-4 py-3">
      <p class="text-[13px] font-semibold text-blue-900">今回の比較</p>
      <p class="mt-1 text-[14px] leading-relaxed text-blue-950">
        今回の条件では <strong>${escapeHtml(carrierName)}</strong>
        ${planName ? `（${escapeHtml(planName)}）` : ""} が
        <strong>請求額・還元込み実質負担・付帯サービス込み</strong> すべて最安です
        （実質 ${formatYenEquivalent(effective?.effective_total)} / 月）
      </p>
    </div>`;
  }

  function summaryPlanName(item) {
    return item?.plan_name || planLabel(item?.lines || []) || "";
  }

  function renderSummarySplit(cheapest, comparisonComplete) {
    if (!comparisonComplete) return "";

    const rows = [
      {
        key: "billing",
        label: "料金だけなら",
        item: cheapest.billing,
        formatter: (item) => `${formatYen(item.billing_total)} / 月`,
      },
      {
        key: "effective",
        label: "還元まで含めると",
        item: cheapest.effective,
        formatter: (item) => `${formatYenEquivalent(item.effective_total)} / 月`,
      },
      {
        key: "valueAdjusted",
        label: "付帯サービスまで含めると",
        item: cheapest.valueAdjusted,
        formatter: (item) => `${formatYenEquivalent(item.value_adjusted_total)} / 月`,
      },
    ].filter((row) => row.item);

    if (allCheapestSamePlan(cheapest)) {
      return renderSummaryCombined(
        rows[0].item.carrier_name,
        summaryPlanName(rows[0].item),
        rows[0].item,
        rows[1].item,
        rows[2].item
      );
    }

    return `<div class="compare-summary__split grid gap-3 sm:grid-cols-3">
      ${rows
        .map(
          (row) => `<div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
          <p class="text-[12px] font-semibold text-slate-600">${escapeHtml(row.label)}</p>
          <p class="mt-1 text-[15px] font-bold text-slate-900">${escapeHtml(row.item.carrier_name)}</p>
          ${
            summaryPlanName(row.item)
              ? `<p class="text-[13px] font-medium text-slate-700">${escapeHtml(summaryPlanName(row.item))}</p>`
              : ""
          }
          <p class="mt-0.5 text-[13px] tabular-nums font-semibold text-slate-700" data-compare-summary="${row.key}">${row.formatter(row.item)}</p>
        </div>`
        )
        .join("")}
      ${
        rows.some((row) => row.key === "valueAdjusted")
          ? `<p class="compare-summary__bundled-note sm:col-span-3 text-[11px] leading-relaxed text-slate-500">※付帯サービス込みは、Pontaパスなどのサービス価値を金額換算した比較用の値です</p>`
          : ""
      }
    </div>`;
  }

  function sortComparisons(comparisons) {
    return [...(comparisons || [])].sort((left, right) => {
      const leftQuotes = getAxisQuotes(left);
      const rightQuotes = getAxisQuotes(right);
      const leftEffective =
        left.status === "ok" ? Number(leftQuotes.effective?.effective_total) : Number.MAX_SAFE_INTEGER;
      const rightEffective =
        right.status === "ok" ? Number(rightQuotes.effective?.effective_total) : Number.MAX_SAFE_INTEGER;
      if (leftEffective !== rightEffective) return leftEffective - rightEffective;
      const leftBilling =
        left.status === "ok" ? Number(leftQuotes.billing?.billing_total) : Number.MAX_SAFE_INTEGER;
      const rightBilling =
        right.status === "ok" ? Number(rightQuotes.billing?.billing_total) : Number.MAX_SAFE_INTEGER;
      if (leftBilling !== rightBilling) return leftBilling - rightBilling;
      return String(left.carrier_id).localeCompare(String(right.carrier_id));
    });
  }

  function setStatusVisibility({ loading = false, error = false, incomplete = false }) {
    document.getElementById("compare-loading")?.classList.toggle("hidden", !loading);
    document.getElementById("compare-error")?.classList.toggle("hidden", !error);
    document.getElementById("compare-incomplete-banner")?.classList.toggle("hidden", !incomplete);
  }

  function renderCompareResult(data, carriersById) {
    const savingsEl = document.getElementById("compare-savings");
    const savingsHintEl = document.getElementById("compare-savings-hint");
    const summaryEl = document.getElementById("compare-summary");
    const gridEl = document.getElementById("compare-carrier-grid");
    if (!summaryEl || !gridEl) return;

    setStatusVisibility({ loading: false, error: false, incomplete: false });

    if (!data) {
      savingsEl?.classList.add("hidden");
      savingsHintEl?.classList.add("hidden");
      summaryEl.classList.add("hidden");
      gridEl.innerHTML = "";
      return;
    }

    const savingsHtml = renderCurrentSavings(data, carriersById);
    if (savingsEl) {
      savingsEl.innerHTML = savingsHtml;
      savingsEl.classList.toggle("hidden", !savingsHtml);
    }
    if (savingsHintEl) {
      const showHint = data.current_cost?.source === "unavailable";
      savingsHintEl.classList.toggle("hidden", !showHint);
    }

    const comparisonComplete = Boolean(data.comparison_complete);
    const cheapest = comparisonComplete
      ? {
          billing: data.cheapest_billing,
          effective: data.cheapest_effective,
          valueAdjusted: data.cheapest_value_adjusted,
        }
      : { billing: null, effective: null, valueAdjusted: null };

    if (!comparisonComplete) {
      setStatusVisibility({ incomplete: true });
    }

    summaryEl.innerHTML = (() => {
      const summaryBody = renderSummarySplit(cheapest, comparisonComplete);
      if (summaryBody.includes("compare-summary__split")) {
        return `<p class="mb-3 text-[13px] font-semibold text-slate-800">今回の比較</p>${summaryBody}`;
      }
      return summaryBody;
    })();
    summaryEl.classList.toggle("hidden", !comparisonComplete && !data.comparisons?.length);

    const sorted = sortComparisons(data.comparisons || []);
    gridEl.innerHTML = sorted
      .map((entry) => renderCarrierCard(entry, cheapest, carriersById))
      .join("");
  }

  function showCompareLoading() {
    setStatusVisibility({ loading: true, error: false, incomplete: false });
    document.getElementById("compare-savings")?.classList.add("hidden");
    document.getElementById("compare-savings-hint")?.classList.add("hidden");
    document.getElementById("compare-summary")?.classList.add("hidden");
    const gridEl = document.getElementById("compare-carrier-grid");
    if (gridEl) gridEl.innerHTML = "";
  }

  function showCompareError() {
    setStatusVisibility({ loading: false, error: true, incomplete: false });
    document.getElementById("compare-savings")?.classList.add("hidden");
    document.getElementById("compare-savings-hint")?.classList.add("hidden");
    document.getElementById("compare-summary")?.classList.add("hidden");
    const gridEl = document.getElementById("compare-carrier-grid");
    if (gridEl) gridEl.innerHTML = "";
  }

  global.CompareUI = {
    formatYen,
    formatYenEquivalent,
    formatPoints,
    aggregateRewards,
    sortComparisons,
    renderCompareResult,
    renderCurrentSavings,
    formatSavingMonthlyText,
    formatSavingAnnualText,
    showCompareLoading,
    showCompareError,
    filterDuplicateRewardStrengths,
    renderCarrierCard,
    renderSummarySplit,
    badgeList,
    getAxisQuotes,
    buildPlanBlockGroups,
    planIdsEqual,
    normalizePlanIds,
    allCheapestSamePlan,
  };
})(window);
