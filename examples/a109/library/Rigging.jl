@block Rigging begin
    # The cockpit controls to the blade angles (ours: the report gives the control positions in
    # percent of travel but no rigging). Each axis maps percent of travel to the angle with the
    # straight line percent = a + b * angle fitted to the report's control-position charts of the
    # fitted model (design/design.py; the README lists the fits):
    #
    #   collective  coll 0 .. 1    = 0 .. 100 % from full down         -> theta0 (deg)
    #   cyclic      lon -1 .. 1    = 0 .. 100 % from full rearward      -> B1 (deg, + forward)
    #               lat -1 .. 1    = 0 .. 100 % from full left          -> A1 (deg, + right)
    #   pedals      ped -1 .. 1    = 100 .. 0 % left pedal forward      -> theta_TR (deg)
    @inputs begin
        coll::Real
        lon::Real
        lat::Real
        ped::Real
    end
    @outputs begin
        th0::Real
        B1::Real
        A1::Real
        thtr::Real
    end
    @parameters begin
        a_coll::Real = 0.0
        b_coll::Real = 1.0
        a_lon::Real = 50.0
        b_lon::Real = 1.0
        a_lat::Real = 50.0
        b_lat::Real = 1.0
        a_ped::Real = 50.0
        b_ped::Real = 1.0
    end
    @equations begin
        th0 ~ (100.0 * coll - a_coll) / b_coll
        B1 ~ (50.0 + 50.0 * lon - a_lon) / b_lon
        A1 ~ (50.0 + 50.0 * lat - a_lat) / b_lat
        thtr ~ (50.0 - 50.0 * ped - a_ped) / b_ped
    end
end
