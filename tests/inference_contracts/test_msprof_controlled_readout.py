from pathlib import Path

from tools.inference_contracts.summarize_msprof_controlled_replay import summarize_controlled_replay


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_summarize_controlled_replay_outputs_small_readout_files(tmp_path):
    source_dir = tmp_path / "runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026"
    analysis_dir = source_dir / "final_analysis"
    output_dir = tmp_path / "runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027"

    write_text(
        source_dir / "generated_token_length_summary.tsv",
        "\t".join(
            [
                "mode",
                "status",
                "request_count",
                "success_case_count",
                "failed_case_count",
                "generated_token_count_mismatch_count",
                "min_generated_token_count",
                "max_generated_token_count",
            ]
        )
        + "\n"
        + "msprof_prefix_cache_on\tsuccess\t1\t1\t0\t0\t64\t64\n"
        + "msprof_prefix_cache_off\tsuccess\t1\t1\t0\t0\t64\t64\n",
    )
    write_text(
        analysis_dir / "prefix_cache_mode_request_delta.tsv",
        "\t".join(
            [
                "case_id",
                "prompt_id",
                "prefix_reuse_group",
                "on_task_row_count",
                "off_task_row_count",
                "delta_task_row_count_on_minus_off",
                "on_total_duration_time",
                "off_total_duration_time",
                "delta_total_duration_time_on_minus_off",
                "on_total_wait_time",
                "off_total_wait_time",
                "delta_total_wait_time_on_minus_off",
                "policy",
            ]
        )
        + "\n"
        + "case_a\tP007\tprefix_group_a\t100\t120\t-20\t1000\t1300\t-300\t0\t0\t0\traw\n",
    )
    write_text(
        analysis_dir / "prefix_pair_candidate_delta.tsv",
        "\t".join(
            [
                "mode",
                "prefix_reuse_group",
                "first_case_id",
                "second_case_id",
                "first_prompt_id",
                "second_prompt_id",
                "first_task_row_count",
                "second_task_row_count",
                "delta_task_row_count_second_minus_first",
                "first_total_duration_time",
                "second_total_duration_time",
                "delta_total_duration_time_second_minus_first",
                "policy",
            ]
        )
        + "\n"
        + "msprof_prefix_cache_on\tprefix_group_a\tcase_a\tcase_b\tP007\tP008\t100\t105\t5\t1000\t900\t-100\tcandidate\n",
    )
    write_text(
        analysis_dir / "request_top_op_type_duration.tsv",
        "\t".join(
            [
                "mode",
                "db_path",
                "case_id",
                "prompt_id",
                "prefix_reuse_group",
                "rank",
                "op_type",
                "task_row_count",
                "total_duration_time",
                "total_wait_time",
            ]
        )
        + "\n"
        + "msprof_prefix_cache_on\t/a.db\tcase_a\tP007\tprefix_group_a\t1\tMatMul\t10\t100\t0\n"
        + "msprof_prefix_cache_off\t/b.db\tcase_a\tP007\tprefix_group_a\t1\tMatMul\t12\t150\t0\n",
    )
    write_text(
        analysis_dir / "request_ai_core_metric_summary.tsv",
        "\t".join(
            [
                "mode",
                "db_path",
                "case_id",
                "prompt_id",
                "prefix_reuse_group",
                "metric_row_count",
                "aic_total_time_sum",
                "aic_mac_ratio_extra_avg",
            ]
        )
        + "\n"
        + "msprof_prefix_cache_on\t/a.db\tcase_a\tP007\tprefix_group_a\t10\t200\t0.5\n"
        + "msprof_prefix_cache_off\t/b.db\tcase_a\tP007\tprefix_group_a\t12\t260\t0.4\n",
    )

    result = summarize_controlled_replay(
        run_id="runtime_vllm_api_msprof_controlled_readout_2026_0708_p1_027",
        source_run_id="runtime_vllm_api_msprof_controlled_replay_2026_0707_p1_026",
        source_artifact_dir=source_dir,
        analysis_dir=analysis_dir,
        generated_token_summary=source_dir / "generated_token_length_summary.tsv",
        artifact_dir=output_dir,
    )

    assert result["overall_status"] == "success"
    assert result["generated_length_status"]["status"] == "fixed_64"
    assert result["missing_files"] == []
    assert "delta_total_duration_time_sum_on_minus_off" in (
        output_dir / "controlled_replay_mode_delta_summary.tsv"
    ).read_text(encoding="utf-8")
    assert "MatMul" in (output_dir / "controlled_replay_top_op_delta.tsv").read_text(encoding="utf-8")
    assert "aic_total_time_sum" in (
        output_dir / "controlled_replay_ai_core_metric_delta.tsv"
    ).read_text(encoding="utf-8")
    assert "mail_ok" in (output_dir / "mail_attachment_candidates.tsv").read_text(encoding="utf-8")
