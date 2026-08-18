"""
Spatial Healthcare Accessibility Pipeline
==========================================
Bronze / Silver / Gold medallion ETL on AWS S3.

Stages
------
1. ingest   – Census 2020 block population + CMS ICF facility data
2. validate – data quality gates
3. transform – standard 2SFCA accessibility computation
4. store    – GeoParquet on S3
5. orchestrate – Airflow DAG (see dags/)
"""

__version__ = "1.0.0"
