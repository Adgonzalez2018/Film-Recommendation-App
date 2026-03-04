import { useCallback, useState } from "react";

export function useRequest(asyncFn){
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const run = useCallback(
        async (...args) => {
            setLoading(true);
            setError(null);
            try{
                return await asyncFn(...args);
            } catch (e) {
                setError(e?.message || "Request failed.");
                throw e;
            } finally {
                setLoading(false);
            }
        },
        [asyncFn]
    );

    return { run, loading, error, setError};
}