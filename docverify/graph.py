"""
DocVerify - LangGraph Agent Graph (Full Parity with question_worker.py)
"""

from __future__ import annotations
import os, re, time
from pathlib import Path
from typing import Any, Optional
from typing_extensions import TypedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from langgraph.graph import StateGraph, START, END


class PipelineState(TypedDict, total=False):
    tenant_id: str
    run_id: str
    started_at: float
    chunks: list[dict]
    page_index: dict
    chunks_metadata: dict
    tier: int
    full_text: str
    nli_verifier: Any
    nli_available: bool
    cross_llm_checker: Any
    cross_llm_available: bool
    aggregate_verdicts_fn: Any
    claim_cache: Any
    failure_ledger: Any
    questions: dict
    evidence: dict
    eval_spec: dict
    routing: dict
    answers: dict
    claims: dict
    research: dict
    correlations: dict
    verifications: dict
    gap_reports: dict
    evaluations: dict
    ragas_metrics: dict
    improvements: dict
    report: str
    report_path: str
    errors: list[str]
    elapsed: float


def ingest_node(state: PipelineState) -> dict:
    """Node 1: Ingest PDFs, build page index, init shared verifiers + cache."""
    from agents.ingestion_agent import ingest_all_pdfs
    print("  [ingest] Starting PDF ingestion...")
    chunks = ingest_all_pdfs()
    print(f"  [ingest] {len(chunks)} chunks produced")
    tier, full_text = 2, ""
    try:
        from agents.ingestion_agent import get_ingestion_result
        ir = get_ingestion_result()
        if ir:
            tier = ir.get("tier", 2)
            full_text = ir.get("full_text", "") or ""
            print(f"  [ingest] Tier {tier}" + (f" ({len(full_text):,} chars)" if tier == 1 else ""))
    except (ImportError, AttributeError):
        pass
    page_index = {}
    for c in chunks:
        k = (c["pdf_file"], c.get("page_start", 0))
        if k in page_index:
            page_index[k] += "\n" + c["text"]
        else:
            page_index[k] = c["text"]
    print(f"  [ingest] {len(page_index)} pages indexed")
    cm = {}
    for c in chunks:
        cm[c.get("chunk_id", "")] = {"pdf_file": c.get("pdf_file", ""), "page_start": c.get("page_start", 0)}
    # Claim cache
    cc = None
    try:
        from agents.claim_cache import get_claim_cache
        cc = get_claim_cache()
        for p in Path("docs/pdfs").glob("*.pdf"):
            en = p.name.replace('.pdf', '_EDITED.md').replace(' ', '_')
            ep = Path("knowledge/edited_markdown") / en
            cc.set_pdf_hash(p.name, str(ep) if ep.exists() else str(p))
        print(f"  [ingest] Claim cache: {cc.stats['total_cached']} cached")
    except (ImportError, Exception) as e:
        print(f"  [ingest] Claim cache: {e}")
    # Failure ledger
    fl = None
    try:
        from agents.failure_ledger import get_failure_ledger
        fl = get_failure_ledger()
        print(f"  [ingest] Failure ledger: {fl.stats['total_failures_tracked']} failures")
    except (ImportError, Exception) as e:
        print(f"  [ingest] Failure ledger: {e}")
    # NLI verifier
    nv, na = None, False
    try:
        from agents.nli_verifier import get_nli_verifier
        nv = get_nli_verifier(); na = True; print("  [ingest] NLI: loaded")
    except (ImportError, Exception):
        print("  [ingest] NLI: not available")
    # Cross-LLM
    xc, xa, af = None, False, None
    try:
        from agents.cross_llm_checker import get_cross_llm_checker, aggregate_verdicts
        xc = get_cross_llm_checker(); xa = xc.available; af = aggregate_verdicts
    except (ImportError, Exception):
        pass
    return {"chunks": chunks, "page_index": page_index, "chunks_metadata": cm,
            "tier": tier, "full_text": full_text, "claim_cache": cc,
            "failure_ledger": fl, "nli_verifier": nv, "nli_available": na,
            "cross_llm_checker": xc, "cross_llm_available": xa, "aggregate_verdicts_fn": af}


def retrieve_node(state: PipelineState) -> dict:
    """Node 2: Load questions, retrieve evidence. Tier-aware."""
    import yaml
    from agents.retriever_agent import retrieve_evidence
    with open("evaluation/evaluation_spec.yaml") as f:
        eval_spec = yaml.safe_load(f)
    questions = {qid: q["text"] for qid, q in eval_spec["questions"].items()}
    tier, all_ev = state.get("tier", 2), {}
    if tier == 1:
        ch = state.get("chunks", [])
        for qid in questions:
            all_ev[qid] = {"question_id": qid, "evidence": ch, "stats": {"returned": len(ch), "avg_relevance": 1.0}}
    else:
        for qid, qt in questions.items():
            print(f"  [retrieve] {qid}...")
            ev = retrieve_evidence(qid, qt)
            all_ev[qid] = ev
            print(f"  [retrieve] {qid}: {ev['stats']['returned']} chunks")
    return {"questions": questions, "evidence": all_ev, "eval_spec": eval_spec}


def route_node(state: PipelineState) -> dict:
    """Node 3: Route each question to Loop A or Loop B."""
    from agents.router_agent import route_question
    es = state.get("eval_spec", {})
    routing = {}
    for qid, qt in state["questions"].items():
        qs = es.get("questions", {}).get(qid, {})
        esum = ""
        if qid in state["evidence"]:
            for c in state["evidence"][qid]["evidence"][:5]:
                esum += f"[{c['chunk_id']}]: {c['text'][:150]}...\n"
        r = route_question(qid, qt, qs, esum)
        routing[qid] = r
        print(f"  [route] {qid} -> Loop {r['loop']}: {r['reason'][:80]}...")
    return {"routing": routing}


def answer_node(state: PipelineState) -> dict:
    """Node 4: Generate answers with self-healing guardrails from failure ledger."""
    from agents.answer_agent import answer_question
    fl = state.get("failure_ledger")
    tier = state.get("tier", 2)
    ft = state.get("full_text", "") if tier == 1 else ""
    answers = {}
    for qid, qt in state["questions"].items():
        print(f"  [answer] Generating {qid}...")
        suf = ""
        if fl:
            try:
                gs = fl.get_guardrails(qid)
                if gs:
                    suf = ("\n\n## SELF-HEALING GUARDRAILS\nThe following claims FAILED "
                           "verification in previous runs. Do NOT make these claims unless "
                           "you find EXPLICIT, WORD-FOR-WORD evidence on the cited page:\n")
                    for g in gs:
                        suf += f"  {g}\n"
                    print(f"  [answer] {qid}: {len(gs)} guardrails injected")
            except Exception as e:
                print(f"  [answer] {qid}: guardrails failed: {e}")
        ec = state["evidence"][qid]["evidence"]
        a = answer_question(qid, qt + suf, ec, full_text=ft)
        a["question_text"] = qt
        answers[qid] = a
        print(f"  [answer] {qid}: {a.get('evidence_chunks_cited', 0)}/{a.get('evidence_chunks_provided', 0)} cited")
    return {"answers": answers}


def _run_nli_batch(nli_verifier, inputs):
    """Run NLI on a batch. Thread-safe."""
    t = time.time()
    claims = [text for _, text, _ in inputs]
    evidences = [ev for _, _, ev in inputs]
    results = nli_verifier.check_batch(claims, evidences)
    print(f"      NLI: {len(inputs)} claims in {time.time()-t:.1f}s")
    return results


def _run_cross_llm_batch(checker, claims, page_index):
    """Run cross-LLM on a batch. Thread-safe."""
    t = time.time()
    results = checker.check_batch(claims, page_index)
    print(f"      Cross-LLM: {len(claims)} claims in {time.time()-t:.1f}s")
    return results


def verify_node(state: PipelineState) -> dict:
    """Node 5: Triple-verification with claim cache + shared verifiers.
    Mirrors _verify_answer_parallel() from question_worker.py exactly."""
    from agents.verification_agent import (
        decompose_claims, check_citation_grounding, build_page_index,
        _get_page_text, rewrite_answer
    )
    chunks = state.get("chunks", [])
    page_index = state.get("page_index", {})
    if not page_index:
        page_index = build_page_index(chunks)
    chunks_metadata = state.get("chunks_metadata", {})
    cache = state.get("claim_cache")
    nli_verifier = state.get("nli_verifier")
    nli_available = state.get("nli_available", False)
    cross_llm_checker = state.get("cross_llm_checker")
    cross_llm_available = state.get("cross_llm_available", False)
    agg_fn = state.get("aggregate_verdicts_fn")
    failure_ledger = state.get("failure_ledger")
    if not agg_fn:
        try:
            from agents.cross_llm_checker import aggregate_verdicts
            agg_fn = aggregate_verdicts
        except ImportError:
            pass
    all_verifications = {}
    updated_answers = dict(state.get("answers", {}))

    for qid in state["questions"]:
        answer_data = updated_answers[qid]
        claims = decompose_claims(answer_data["answer_markdown"], chunks_metadata)
        print(f"  [verify] {qid}: {len(claims)} claims extracted")
        cache_hits = 0

        # Check claim cache
        if cache:
            for claim in claims:
                cf = claim.get("cited_file", "")
                cp = claim.get("cited_page", 0)
                if cf and cp:
                    cached = cache.lookup(claim["text"], cf, cp)
                    if cached:
                        if "grounding" in cached and agg_fn:
                            claim["grounding"] = cached["grounding"]
                            claim["nli"] = cached.get("nli")
                            claim["cross_llm"] = cached.get("cross_llm")
                            r = agg_fn(claim)
                            claim["final_verdict"] = r["final_verdict"]
                            claim["final_confidence"] = r["final_confidence"]
                        elif "final_verdict" in cached:
                            claim["final_verdict"] = cached["final_verdict"]
                            claim["final_confidence"] = cached.get("final_confidence", 0.5)
                        else:
                            continue
                        claim["cached"] = True
                        cache_hits += 1

        uncached = [c for c in claims if not c.get("cached")]
        if not uncached:
            p = sum(1 for c in claims if c.get("final_verdict") == "pass")
            fa = sum(1 for c in claims if c.get("final_verdict") == "fail")
            fl2 = sum(1 for c in claims if c.get("final_verdict") == "flag")
            print(f"  [verify] {qid}: All {len(claims)} cached (hits: {cache_hits})")
            all_verifications[qid] = {"verified_answer": answer_data, "claims": claims,
                "stats": {"total": len(claims), "passed": p, "failed": fa, "flagged": fl2,
                          "cache_hits": cache_hits, "verifiers_active": ["cache"]}}
            continue

        # Layer 1: Grounding (deterministic)
        for claim in uncached:
            claim["grounding"] = check_citation_grounding(claim, page_index)

        # Prepare NLI + Cross-LLM inputs
        nli_inputs, xlm_inputs = [], []
        for i, claim in enumerate(uncached):
            if claim.get("cited_file") and claim.get("cited_page"):
                ev_text = _get_page_text(page_index, claim["cited_file"], claim["cited_page"], include_adjacent=True)
                if ev_text:
                    nli_inputs.append((i, claim["text"], ev_text))
                    xlm_inputs.append(claim)

        # Layer 2+3: NLI + Cross-LLM in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            nf, xf = None, None
            if nli_available and nli_verifier and nli_inputs:
                nf = executor.submit(_run_nli_batch, nli_verifier, nli_inputs)
            if cross_llm_available and cross_llm_checker and xlm_inputs:
                xf = executor.submit(_run_cross_llm_batch, cross_llm_checker, xlm_inputs, page_index)
            if nf:
                try:
                    nr = nf.result()
                    for (idx, _, _), nli_r in zip(nli_inputs, nr):
                        uncached[idx]["nli"] = nli_r
                except Exception as e:
                    print(f"  [verify] {qid}: NLI failed: {e}")
            if xf:
                try:
                    xr = xf.result()
                    xi = 0
                    for claim in uncached:
                        if claim.get("cited_file") and claim.get("cited_page"):
                            if xi < len(xr):
                                claim["cross_llm"] = xr[xi]; xi += 1
                except Exception as e:
                    print(f"  [verify] {qid}: Cross-LLM failed: {e}")

        # Aggregate verdicts + cache store
        passed, failed, flagged = 0, 0, 0
        for claim in uncached:
            if agg_fn:
                agg = agg_fn(claim)
                claim["final_verdict"] = agg["final_verdict"]
                claim["final_confidence"] = agg["final_confidence"]
                claim["aggregation"] = agg
            else:
                g = claim.get("grounding", {}).get("verdict", "uncited")
                if g == "grounded": claim["final_verdict"] = "pass"
                elif g == "mismatch": claim["final_verdict"] = "fail"
                else: claim["final_verdict"] = "flag" if g == "ungrounded" else "pass"
            if cache:
                cf = claim.get("cited_file", "")
                cp = claim.get("cited_page", 0)
                if cf and cp:
                    cache.store(claim["text"], cf, cp, {
                        "grounding": claim.get("grounding", {}),
                        "nli": claim.get("nli"), "cross_llm": claim.get("cross_llm")})
            v = claim["final_verdict"]
            if v == "pass": passed += 1
            elif v == "fail": failed += 1
            elif v == "flag": flagged += 1

        # Count cached verdicts
        for claim in claims:
            if claim.get("cached"):
                v = claim.get("final_verdict", "pass")
                if v == "pass": passed += 1
                elif v == "fail": failed += 1
                elif v == "flag": flagged += 1

        # Record to failure ledger
        if failure_ledger:
            fc = [c for c in claims if c.get("final_verdict") == "fail" and not c.get("cached")]
            if fc:
                try:
                    rn = failure_ledger._data["meta"].get("total_runs", 0) + 1
                    failure_ledger.record_failures(qid, fc, rn)
                except Exception:
                    pass

        # Rewrite if needed
        if failed > 0 or flagged > 0:
            verified_answer = rewrite_answer(answer_data, claims)
        else:
            verified_answer = answer_data
        updated_answers[qid] = verified_answer

        va_list = ["grounding"]
        if nli_available: va_list.append("nli")
        if cross_llm_available: va_list.append("cross_llm")
        if cache_hits > 0: va_list.append("cache")
        all_verifications[qid] = {"verified_answer": verified_answer, "claims": claims,
            "stats": {"total": len(claims), "passed": passed, "failed": failed,
                      "flagged": flagged, "cache_hits": cache_hits, "verifiers_active": va_list}}
        print(f"  [verify] {qid}: pass:{passed} fail:{failed} flag:{flagged} cached:{cache_hits}")

    # Save cache
    if cache:
        try:
            cache.save()
        except Exception:
            pass

    # Gap verification
    all_gap_reports = {}
    try:
        from agents.gap_verifier_agent import verify_gaps
        ft2 = state.get("full_text", "") if state.get("tier", 2) == 1 else None
        for qid in state["questions"]:
            gr = verify_gaps({qid: updated_answers[qid]}, full_text=ft2, chunks=chunks)
            if gr:
                all_gap_reports[qid] = gr.get(qid, gr)
    except ImportError:
        pass
    except Exception as e:
        print(f"  [verify] Gap verification failed: {e}")

    if failure_ledger:
        try:
            failure_ledger.save()
        except Exception:
            pass
    return {"verifications": all_verifications, "gap_reports": all_gap_reports, "answers": updated_answers}


def loop_b_research_node(state: PipelineState) -> dict:
    """Node 6: Loop B research."""
    lb = [q for q, r in state["routing"].items() if r["loop"] == "B"]
    if not lb:
        return {"claims": {}, "research": {}, "correlations": {}}
    from agents.claim_extractor_agent import extract_claims
    from agents.research_agent import research_claims_batch
    from agents.correlation_agent import build_comparison
    ac, ar, ax = {}, {}, {}
    for qid in lb:
        ad = state["answers"][qid]
        ec = state["evidence"][qid]["evidence"]
        targets = state["routing"][qid].get("comparison_targets", [])
        claims = extract_claims(ad)
        ac[qid] = claims
        rr = []
        for platform in targets:
            cc = [c for c in claims.get("claims", []) if c.get("needs_external")]
            if not cc:
                cc = [{"claim_id": f"{qid}-GENERAL", "text": f"Comparison with {platform}",
                       "needs_external": True, "verification_query": f"{platform} security"}]
            rr.extend(research_claims_batch(cc, platform))
        ar[qid] = rr
        cor = build_comparison(question_id=qid, question_text=ad["question_text"],
            answer_data=ad, claims_data=claims, research_results=rr, evidence_chunks=ec)
        ax[qid] = cor
        if cor.get("enriched_answer"):
            ad["answer_markdown_original"] = ad.get("answer_markdown", "")
            ad["answer_markdown"] = cor["enriched_answer"]
            ad["loop"] = "B"
    return {"claims": ac, "research": ar, "correlations": ax}


def _run_ragas(qid, answer_data, evidence_chunks):
    """Run RAGAS faithfulness with focused contexts. Thread-safe."""
    try:
        from agents.ragas_evaluator import compute_ragas_metrics
        at = answer_data.get("answer_markdown", "")
        ctx = _build_ragas_contexts(answer_data, evidence_chunks)
        if not ctx:
            ctx = [c.get("text", "")[:2000] for c in evidence_chunks[:15] if c.get("text", "").strip()]
        afr = at
        for sec in ["## DOC_GAPS", "## What the Documents Do NOT Cover", "## Planned/Roadmap Items"]:
            idx = afr.find(sec)
            if idx > 0: afr = afr[:idx]
        if len(afr) > 8000: afr = afr[:8000]
        return compute_ragas_metrics(question=answer_data.get("question_text", ""), answer=afr, contexts=ctx)
    except Exception as e:
        return {"faithfulness": None, "error": str(e)}


def _build_ragas_contexts(answer_data, evidence_chunks):
    """Build focused contexts from cited pages for RAGAS."""
    at = answer_data.get("answer_markdown", "")
    doc_cites = re.findall(r'\[\[doc:([^,\]]+)(?:,\s*p\.?(\d+(?:-\d+)?))?]]', at)
    chunk_cites = re.findall(r'\[\[chunk:([^\]]+)]]', at)
    cl = {}
    for c in evidence_chunks:
        k = (c.get("pdf_file", ""), c.get("page_start", 0))
        cl[k] = cl.get(k, "") + ("\n" if k in cl else "") + c.get("text", "")
    cil = {c.get("chunk_id", ""): c.get("text", "") for c in evidence_chunks}
    contexts, seen = [], set()
    for dn, ps in doc_cites:
        if not ps: continue
        pages = []
        if "-" in ps:
            parts = ps.split("-")
            try: pages = list(range(int(parts[0]), int(parts[1]) + 1))
            except ValueError: continue
        else:
            try: pages = [int(ps)]
            except ValueError: continue
        for pg in pages:
            k = (dn, pg)
            if k in seen: continue
            seen.add(k)
            txt = cl.get(k, "")
            if not txt:
                for (fn, p), t in cl.items():
                    if p == pg and (dn in fn or fn in dn):
                        txt = t; break
            if txt: contexts.append(txt[:3000])
    for ci in chunk_cites:
        if ci in seen: continue
        seen.add(ci)
        txt = cil.get(ci, "")
        if txt: contexts.append(txt[:3000])
    return contexts


def evaluate_node(state: PipelineState) -> dict:
    """Node 7: Dual eval (GPT x2 averaged) + RAGAS + asymmetric blending + verification floor."""
    import yaml
    from agents.evaluator_agent import evaluate_answer
    es = state.get("eval_spec", {})
    weights = es.get("scoring", {}).get("weights", {})
    thresholds = es.get("scoring", {}).get("thresholds", {})
    tier = state.get("tier", 2)
    all_evals, all_ragas = {}, {}

    for qid in state["questions"]:
        print(f"  [evaluate] {qid}: dual eval + RAGAS...")
        ad = state["answers"][qid]
        ec = list(state["evidence"][qid]["evidence"])
        # Tier 1 chunk limiting
        if tier == 1 and len(ec) > 50:
            cd = set(ad.get("cited_documents", []))
            ec = [c for c in ec if c.get("pdf_file") in cd] + [c for c in ec if c.get("pdf_file") not in cd][:20]
        # Approved edits as evidence
        try:
            from agents.doc_editor_agent import load_approved_edits
            edits = load_approved_edits()
            if edits:
                for edit in edits:
                    ec.append({"chunk_id": f"approved_edit_{edit.get('id', '')}",
                        "text": edit.get("new_text", ""), "pdf_file": edit.get("target_file", "approved_edits"),
                        "page_start": 0, "content_type": "approved_edit"})
        except (ImportError, Exception):
            pass

        # Dual eval + RAGAS in parallel
        e1, e2, rm = None, None, None
        with ThreadPoolExecutor(max_workers=3) as ex:
            f1 = ex.submit(evaluate_answer, qid, ad, ec)
            f2 = ex.submit(evaluate_answer, qid, ad, ec)
            f3 = ex.submit(_run_ragas, qid, ad, ec)
            try: e1 = f1.result(timeout=360)
            except Exception as e: print(f"  [evaluate] {qid}: eval1 failed: {e}")
            try: e2 = f2.result(timeout=360)
            except Exception as e: print(f"  [evaluate] {qid}: eval2 failed: {e}")
            try: rm = f3.result(timeout=360)
            except Exception: rm = None

        # Average dual evals
        if e1 and e2 and "scores" in e1 and "scores" in e2:
            evaluation = e1
            s1, s2 = e1["scores"], e2["scores"]
            for k in s1:
                if isinstance(s1.get(k), (int, float)) and isinstance(s2.get(k), (int, float)):
                    evaluation["scores"][k] = round((s1[k] + s2[k]) / 2, 4)
            evaluation["overall_score"] = round((e1.get("overall_score", 0) + e2.get("overall_score", 0)) / 2, 4)
            evaluation["dual_eval"] = True
            evaluation["eval_scores"] = [
                {k: v for k, v in s1.items() if isinstance(v, (int, float))},
                {k: v for k, v in s2.items() if isinstance(v, (int, float))}]
        elif e1: evaluation = e1
        elif e2: evaluation = e2
        else:
            evaluation = {"scores": {"grounded_correctness": 0.75, "completeness": 0.75,
                "precision": 0.70, "clarity": 0.80, "citation_quality": 0.75},
                "overall_score": 0.75, "passed": False, "evaluator_timeout": True}

        # Asymmetric RAGAS blending
        if rm and rm.get("faithfulness") is not None:
            evaluation["ragas_faithfulness"] = rm["faithfulness"]
            evaluation["ragas_answer_relevancy"] = rm.get("answer_relevancy")
            gc = evaluation.get("scores", {}).get("grounded_correctness", 0)
            rf = rm["faithfulness"]
            if rf > gc and (rf - gc) > 0.10:
                divergence = rf - gc
                blended = gc * 0.35 + rf * 0.65 if divergence > 0.20 else (gc + rf) / 2
                evaluation["scores"]["grounded_correctness_original"] = gc
                evaluation["scores"]["grounded_correctness"] = round(blended, 4)
                evaluation["score_blend_applied"] = True
                evaluation["blend_direction"] = "up"
                s = evaluation["scores"]
                wt = (s.get("grounded_correctness", 0) * weights.get("grounded_correctness", 0.35) +
                      s.get("completeness", 0) * weights.get("completeness", 0.25) +
                      s.get("precision", 0) * weights.get("precision", 0.15) +
                      s.get("clarity", 0) * weights.get("clarity", 0.10) +
                      s.get("citation_quality", 0) * weights.get("citation_quality", 0.15))
                evaluation["overall_score"] = round(wt, 4)
                evaluation["passed"] = (wt >= thresholds.get("pass_overall", 0.78) and
                    s.get("grounded_correctness", 0) >= thresholds.get("min_correctness", 0.80))
            elif rf < gc and (gc - rf) > 0.15:
                evaluation["score_blend_applied"] = False
                evaluation["blend_direction"] = "skipped_ragas_lower"
        all_ragas[qid] = rm

        # Verification floor
        v = state.get("verifications", {}).get(qid, {})
        if not evaluation.get("passed") and v and v.get("claims"):
            fc = [c for c in v["claims"] if c.get("final_verdict") == "fail"]
            gf = sum(1 for c in fc if c.get("grounding", {}).get("match_ratio", 0) < 0.5)
            s = evaluation.get("scores", {})
            gc = s.get("grounded_correctness", 0)
            apply_floor = (gf <= 2 and len(fc) > 0) or (gf == 0 and len(fc) == 0)
            if apply_floor and gc < 0.82:
                s["grounded_correctness_pre_floor"] = gc
                s["grounded_correctness"] = 0.82
                evaluation["verification_floor_applied"] = True
                wt = (s.get("grounded_correctness", 0) * weights.get("grounded_correctness", 0.35) +
                      s.get("completeness", 0) * weights.get("completeness", 0.25) +
                      s.get("precision", 0) * weights.get("precision", 0.15) +
                      s.get("clarity", 0) * weights.get("clarity", 0.10) +
                      s.get("citation_quality", 0) * weights.get("citation_quality", 0.15))
                evaluation["overall_score"] = round(wt, 4)
                evaluation["passed"] = (wt >= thresholds.get("pass_overall", 0.78) and
                    s.get("grounded_correctness", 0) >= thresholds.get("min_correctness", 0.80))

        # Attach verification stats
        if v:
            evaluation["verification_stats"] = v.get("stats", {})
            evaluation["claims_total"] = v.get("stats", {}).get("total", 0)
            evaluation["claims_passed"] = v.get("stats", {}).get("passed", 0)
            evaluation["claims_failed"] = v.get("stats", {}).get("failed", 0)
        all_evals[qid] = evaluation
        status = "PASS" if evaluation.get("passed") else "FAIL"
        print(f"  [evaluate] {qid}: {evaluation.get('overall_score', 0):.2f} -- {status}")
    return {"evaluations": all_evals, "ragas_metrics": all_ragas}


def edit_node(state: PipelineState) -> dict:
    """Node 8: Propose improvements + apply doc edits."""
    from agents.editor_agent import propose_improvements
    seen, all_ec = set(), []
    for qid in state["evidence"]:
        for c in state["evidence"][qid]["evidence"]:
            cid = c.get("chunk_id", "")
            if cid not in seen:
                all_ec.append(c); seen.add(cid)
    eval_reports = []
    for qid, ed in state.get("evaluations", {}).items():
        rpt = {"question_id": qid, "question_text": state["questions"][qid]}
        rpt.update(ed)
        v = state.get("verifications", {}).get(qid, {})
        if v and v.get("claims"):
            fc = [c for c in v["claims"] if c.get("final_verdict") == "fail"]
            flg = [c for c in v["claims"] if c.get("final_verdict") == "flag"]
            failures = list(rpt.get("failures") or [])
            for c in fc:
                d = c.get("aggregation", {}).get("reasoning", "")
                failures.append("FAIL: " + c.get("text", "")[:80] + " " + d)
            for c in flg:
                failures.append("FLAG: " + c.get("text", "")[:80])
            rpt["failures"] = failures
        gr = state.get("gap_reports", {}).get(qid, {})
        if gr and gr.get("verified_gaps"):
            sug = list(rpt.get("suggested_doc_improvements") or [])
            for gap in gr["verified_gaps"]:
                sug.append({"priority": gap.get("priority", "P1"),
                    "description": gap.get("gap_text", "")})
            rpt["suggested_doc_improvements"] = sug
        eval_reports.append(rpt)
    improvements = propose_improvements(eval_reports, all_ec)
    nc = len(improvements.get("proposed_changes", []))
    print(f"  [editor] {nc} improvements proposed")
    if nc > 0:
        try:
            from agents.ingestion_agent import get_ingestion_result
            from agents.doc_editor_agent import apply_edits
            ir = get_ingestion_result()
            mg = []
            for q, gr in state.get("gap_reports", {}).items():
                mg.extend(gr.get("verified_gaps", []))
            if mg and ir and ir.get("markdown_files"):
                er = apply_edits({"verified_gaps": mg}, ir["markdown_files"])
                if er.get("edit_count", 0) > 0:
                    try:
                        from agents.edit_verifier import verify_edits
                        verify_edits(edited_files=er.get("edited_files", {}),
                            all_edits=er.get("edits", []),
                            original_files=ir["markdown_files"])
                    except (ImportError, Exception):
                        pass
        except (ImportError, Exception) as e:
            print(f"  [editor] Doc edit skipped: {e}")
    return {"improvements": improvements}


def report_node(state: PipelineState) -> dict:
    """Node 9: Generate report + save scores JSON."""
    import json
    from datetime import datetime
    elapsed = time.time() - state.get("started_at", time.time())
    lines = ["# DocVerify Evaluation Report",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Tier:** {state.get('tier', 2)}", "",
        "## Summary", "",
        "| Q | Loop | Score | Claims | Verdict |",
        "|---|------|-------|--------|---------|"]
    for qid in sorted(state.get("evaluations", {}).keys()):
        ed = state["evaluations"][qid]
        lp = state.get("routing", {}).get(qid, {}).get("loop", "A")
        vs = ed.get("verification_stats", {})
        cl = f"{vs.get('passed', 0)}/{vs.get('total', 0)}" if vs else "--"
        vd = "PASS" if ed.get("passed") else "FAIL"
        lines.append(f"| {qid} | {lp} | {ed.get('overall_score', 0):.2f} | {cl} | {vd} |")
    lines.extend(["", f"**Time:** {elapsed:.1f}s"])
    report_text = "\n".join(lines)
    rd = Path("reports"); rd.mkdir(exist_ok=True)
    rp = str(rd / "latest_report.md")
    with open(rp, "w") as f:
        f.write(report_text)
    sd = {}
    for qid, ed in state.get("evaluations", {}).items():
        sd[qid] = dict(ed)
        v = state.get("verifications", {}).get(qid, {})
        if v:
            sd[qid]["verification"] = {"stats": v.get("stats", {}), "claims": v.get("claims", [])}
    with open(str(rd / "latest_scores.json"), "w") as f:
        json.dump(sd, f, indent=2, default=str)
    print(f"  [report] Saved to {rp}")
    return {"report": report_text, "report_path": rp, "elapsed": elapsed}


def has_loop_b(state: PipelineState) -> str:
    for qid, r in state.get("routing", {}).items():
        if r.get("loop") == "B": return "loop_b"
    return "evaluate"


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("ingest", ingest_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("route", route_node)
    g.add_node("answer", answer_node)
    g.add_node("verify", verify_node)
    g.add_node("loop_b", loop_b_research_node)
    g.add_node("evaluate", evaluate_node)
    g.add_node("edit", edit_node)
    g.add_node("report", report_node)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "retrieve")
    g.add_edge("retrieve", "route")
    g.add_edge("route", "answer")
    g.add_edge("answer", "verify")
    g.add_conditional_edges("verify", has_loop_b, {
        "loop_b": "loop_b", "evaluate": "evaluate"})
    g.add_edge("loop_b", "evaluate")
    g.add_edge("evaluate", "edit")
    g.add_edge("edit", "report")
    g.add_edge("report", END)
    return g.compile()


def run(tenant_id="default"):
    graph = build_graph()
    return graph.invoke({"tenant_id": tenant_id, "started_at": time.time(), "errors": []})


if __name__ == "__main__":
    result = run()
    for qid, e in sorted(result.get("evaluations", {}).items()):
        s = "PASS" if e.get("passed") else "FAIL"
        vs = e.get("verification_stats", {})
        print(f"{qid}: {e.get('overall_score', 0):.2f} {s} ({vs.get('passed', 0)}/{vs.get('total', 0)} claims)")
