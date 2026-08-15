from frontend_paths import find_frontend_dist


def test_find_frontend_dist_supports_flat_container_layout(tmp_path):
    module_dir = tmp_path / "app"
    expected = module_dir / "frontend" / "dist"
    expected.mkdir(parents=True)

    assert find_frontend_dist(module_dir) == expected


def test_find_frontend_dist_supports_source_repository_layout(tmp_path):
    module_dir = tmp_path / "repo" / "backend"
    expected = tmp_path / "repo" / "frontend" / "dist"
    expected.mkdir(parents=True)

    assert find_frontend_dist(module_dir) == expected
