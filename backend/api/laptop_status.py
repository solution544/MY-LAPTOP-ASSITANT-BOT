from fastapi import APIRouter

from backend.core.laptop_manager import laptop_manager


router = APIRouter(
    prefix="/api/laptop",
    tags=["Laptop"],
)


@router.get("/status")
async def laptop_status():
    laptops = await laptop_manager.list_connected()

    return {
        "online": len(laptops) > 0,
        "count": len(laptops),
        "laptops": [
            {
                "device_id": laptop.device_id,
                "hostname": laptop.hostname,
                "os": laptop.os_name,
                "os_version": laptop.os_version,
                "connected_at": laptop.connected_at.isoformat(),
                "last_seen": laptop.last_seen.isoformat(),
                "pending_commands": len(
                    laptop.pending_commands
                ),
            }
            for laptop in laptops
        ],
    }