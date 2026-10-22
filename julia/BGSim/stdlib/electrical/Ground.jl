@block Ground begin
    @ports p::Power{Electrical}
    @equations p.e ~ 0.0
    @causality p => (:effort_out, :fixed)
end
