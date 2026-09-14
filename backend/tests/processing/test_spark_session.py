from processing.spark_session import SparkConfig, build_spark_conf, s3a_uri


def test_minio_endpoint_enables_path_style_without_ssl():
    conf = build_spark_conf(SparkConfig(s3_endpoint_url="http://minio:9000"))

    assert conf["spark.hadoop.fs.s3a.endpoint"] == "http://minio:9000"
    assert conf["spark.hadoop.fs.s3a.path.style.access"] == "true"
    assert conf["spark.hadoop.fs.s3a.connection.ssl.enabled"] == "false"


def test_real_s3_leaves_endpoint_and_credentials_to_defaults():
    conf = build_spark_conf(SparkConfig())

    assert "spark.hadoop.fs.s3a.endpoint" not in conf
    assert "spark.hadoop.fs.s3a.aws.credentials.provider" not in conf


def test_static_credentials_use_simple_provider():
    conf = build_spark_conf(SparkConfig(aws_access_key_id="key", aws_secret_access_key="secret"))

    assert conf["spark.hadoop.fs.s3a.access.key"] == "key"
    assert conf["spark.hadoop.fs.s3a.secret.key"] == "secret"
    assert conf["spark.hadoop.fs.s3a.aws.credentials.provider"].endswith(
        "SimpleAWSCredentialsProvider"
    )


def test_jars_dir_is_expanded_into_spark_jars(tmp_path):
    (tmp_path / "b.jar").touch()
    (tmp_path / "a.jar").touch()
    (tmp_path / "notes.txt").touch()

    conf = build_spark_conf(SparkConfig(jars_dir=str(tmp_path)))

    assert conf["spark.jars"] == f"{tmp_path}/a.jar,{tmp_path}/b.jar"


def test_adaptive_query_execution_enabled():
    conf = build_spark_conf(SparkConfig(shuffle_partitions=16))

    assert conf["spark.sql.adaptive.enabled"] == "true"
    assert conf["spark.sql.shuffle.partitions"] == "16"


def test_s3a_uri_strips_leading_slash():
    assert s3a_uri("datasets", "/samples/a.csv") == "s3a://datasets/samples/a.csv"


def test_input_partition_size_is_configurable():
    assert build_spark_conf(SparkConfig())["spark.sql.files.maxPartitionBytes"] == "128m"
    conf = build_spark_conf(SparkConfig(max_partition_bytes="16m"))
    assert conf["spark.sql.files.maxPartitionBytes"] == "16m"


def test_unparseable_dates_become_null_rather_than_failing():
    assert build_spark_conf(SparkConfig())["spark.sql.legacy.timeParserPolicy"] == "CORRECTED"
