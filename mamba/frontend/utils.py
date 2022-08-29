def slot_gen(obj, typs0, typs1):
    if not typs0:
        typs0 = typs1
    handles = {typ0: getattr(obj, "on_" + typ1)
        for typ0, typ1 in zip(typs0, typs1)}
    def slot(args):
        hdl = handles.get(args[0])
        hdl and hdl(*args[1:])
    return slot

def model_connect(obj, model, typs0, typs1):
    obj.model = model
    model.sigNote.connect(slot_gen(obj, typs0, typs1))

