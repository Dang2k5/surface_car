from agent.graph.builder import build_qc_graph, export_graph_mermaid
from agent.services.repository import PostgresQCRepository
from agent.services.verifier import ModelVerifier
from agent.services.yolo_detector import LocalYoloSegmentationDetector
from backend.app.config import ModelSettings
from backend.app.database import Database
from backend.app.main import get_database_url

if __name__ == "__main__":
    settings = ModelSettings.from_env()
    detector = LocalYoloSegmentationDetector(
        settings.model_path,
        device=settings.model_device,
        confidence=settings.model_confidence,
        image_size=settings.model_image_size,
        fixed_calibration_enabled=settings.fixed_camera_calibration_enabled,
        mm_per_pixel_x=settings.calibration_mm_per_pixel_x,
        mm_per_pixel_y=settings.calibration_mm_per_pixel_y,
        calibration_profile_id=settings.calibration_profile_id,
    )
    verifier = ModelVerifier(detector, min_confidence=settings.verify_threshold)
    database = Database(get_database_url())
    repository = PostgresQCRepository(database)
    export_graph_mermaid(
        build_qc_graph(detector=detector, verifier=verifier, repository=repository),
        "agent_flow.mmd",
    )
    database.close()
