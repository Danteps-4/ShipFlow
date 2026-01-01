import { useEffect, useState } from 'react';
import api from '../api';
import { Store, ShoppingBag, Plus, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface StoreData {
    id: number;
    name: string;
    tiendanube_user_id: number;
}

export default function Stores() {
    const [stores, setStores] = useState<StoreData[]>([]);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchStores = async () => {
            try {
                const response = await api.get('/api/me/stores');
                setStores(response.data);
            } catch (err) {
                console.error("Error fetching stores", err);
            } finally {
                setLoading(false);
            }
        };
        fetchStores();
    }, []);

    const handleConnect = async () => {
        try {
            const response = await api.get('/tiendanube/connect-url');
            if (response.data.url) {
                window.location.href = response.data.url;
            }
        } catch (err) {
            console.error("Error getting connect url", err);
            alert("Error al conectar con Tienda Nube");
        }
    };

    const handleLogout = () => {
        localStorage.removeItem('access_token');
        navigate('/login');
    }

    const handleSelectStore = (storeId: number) => {
        // Here we could set active store in context or just navigate
        // For MVP, maybe we don't have a dashboard yet, but let's placeholder it
        localStorage.setItem('active_store_id', storeId.toString());
        alert(`Seleccionada tienda ${storeId}. (Dashboard pendiente en MVP)`);
        // navigate(`/store/${storeId}`); 
    };

    if (loading) {
        return <div className="flex justify-center items-center h-screen">Cargando tiendas...</div>;
    }

    return (
        <div className="min-h-screen bg-gray-50">
            <nav className="bg-white shadow">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between h-16">
                        <div className="flex items-center">
                            <span className="text-xl font-bold text-gray-800">Shipflow</span>
                        </div>
                        <div className="flex items-center">
                            <button onClick={handleLogout} className="text-gray-600 hover:text-gray-900 flex items-center gap-2">
                                <LogOut size={18} /> Salir
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-extrabold text-gray-900">Mis Tiendas</h1>
                    <p className="mt-2 text-gray-600">Selecciona una tienda para gestionar envíos</p>
                </div>

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    {/* Store Cards */}
                    {stores.map((store) => (
                        <div key={store.id} onClick={() => handleSelectStore(store.id)} className="bg-white overflow-hidden shadow rounded-lg hover:shadow-lg transition-shadow cursor-pointer border border-transparent hover:border-blue-500">
                            <div className="p-6 flex items-center gap-4">
                                <div className="bg-blue-100 p-3 rounded-full">
                                    <Store className="w-6 h-6 text-blue-600" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-medium text-gray-900">{store.name}</h3>
                                    <p className="text-sm text-gray-500">ID: {store.tiendanube_user_id}</p>
                                </div>
                            </div>
                        </div>
                    ))}

                    {/* Add New Card */}
                    <div onClick={handleConnect} className="bg-gray-50 overflow-hidden shadow-sm rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-500 hover:bg-gray-100 transition-colors cursor-pointer flex flex-col items-center justify-center p-6 min-h-[120px]">
                        <Plus className="w-8 h-8 text-gray-400 mb-2" />
                        <span className="text-gray-600 font-medium">Conectar nueva tienda</span>
                        <div className="flex items-center mt-1 text-xs text-gray-400">
                            <ShoppingBag size={12} className="mr-1" /> Tienda Nube
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
